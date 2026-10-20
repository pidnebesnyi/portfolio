"""The app's structured log as evidence: what happened to a request can be read back afterwards.

Every request gets an id (X-Request-ID, taken from the caller when it is a plain token, else
generated); its access line and the domain events it caused carry that id. These tests read the
log file the app writes, find a request's lines by the id from the response header, and check
them. No sleeps: the access line is written after the response, so the helper polls for it.
"""

import re
from uuid import uuid4

import allure
import pytest

from tests.clients.auth_api import AuthApi
from tests.clients.http import LoggedHttpClient
from tests.clients.payments_api import PaymentsApi
from tests.config import Settings
from tests.factories.merchant_factory import MerchantAccount, MerchantFactory
from tests.factories.payment_factory import PaymentFactory
from tests.models.logs import LogLine
from tests.models.payments import PaymentStatus
from tests.utils.allure_links import area, requirement
from tests.utils.app_log import ACCESS_EVENT, AppLog
from tests.utils.tokens import totp_code

pytestmark = [area("Request log"), requirement("OBS-LOG")]

GENERATED_ID = re.compile(r"^[0-9a-f]{32}$")


def _events(lines: list[LogLine]) -> list[str]:
    """Event names of a request in the order written, without the broker bookkeeping lines."""
    return [line.event for line in lines if not line.event.startswith("event.")]


def _one(lines: list[LogLine], event: str) -> LogLine:
    (found,) = (line for line in lines if line.event == event)
    return found


@pytest.mark.smoke
@allure.title("The access line of a request carries the response's request id and the merchant")
def test_access_line_carries_the_response_request_id_and_the_merchant(
    api: PaymentsApi, merchant: MerchantAccount, app_log: AppLog
) -> None:
    response = api.list_payments()
    request_id = response.headers["X-Request-ID"]

    access = _one(app_log.request(request_id), ACCESS_EVENT)

    assert (access.method, access.path, access.status) == ("GET", "/payments", 200)
    assert access.merchant_id == str(merchant.id)
    assert access.duration_ms is not None
    assert access.duration_ms >= 0


@pytest.mark.regression
@allure.title("A valid X-Request-ID from the caller is kept and used in the log")
def test_a_valid_request_id_from_the_caller_is_kept(
    http: LoggedHttpClient, app_log: AppLog
) -> None:
    sent = f"qa-{uuid4()}"

    response = http.request("GET", "/health", headers={"X-Request-ID": sent})

    assert response.headers["X-Request-ID"] == sent
    assert _one(app_log.request(sent), ACCESS_EVENT).path == "/health"


@pytest.mark.regression
@pytest.mark.parametrize(
    "bad_id",
    ["short", "has spaces in it", "x" * 65, 'quote"{"event":"forged"}'],
    ids=["too-short", "spaces", "too-long", "json-injection"],
)
@allure.title("An unusable X-Request-ID is replaced by a generated one: {bad_id}")
def test_an_unusable_request_id_is_replaced(
    http: LoggedHttpClient, app_log: AppLog, bad_id: str
) -> None:
    response = http.request("GET", "/health", headers={"X-Request-ID": bad_id})

    request_id = response.headers["X-Request-ID"]
    assert GENERATED_ID.match(request_id), f"expected a generated id, got {request_id!r}"
    app_log.request(request_id)
    assert bad_id not in app_log.text(), "the rejected value must not reach the log"


@pytest.mark.regression
@allure.title("An unauthenticated request is logged without a merchant")
def test_an_unauthenticated_request_is_logged_without_a_merchant(
    api: PaymentsApi, app_log: AppLog
) -> None:
    response = api.with_token(None).list_payments()
    assert response.status_code == 401

    access = _one(app_log.request(response.headers["X-Request-ID"]), ACCESS_EVENT)

    assert (access.status, access.merchant_id) == (401, None)


@pytest.mark.regression
@allure.title("A refund logs its events in order, all under the request's id")
def test_a_refund_logs_its_events_in_order(
    api: PaymentsApi, payment_factory: PaymentFactory, app_log: AppLog
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=1000)
    refund = api.refund(payment.id, 300)

    lines = app_log.request(refund.raw.headers["X-Request-ID"])

    assert _events(lines) == ["refund.accepted", "payment.status_changed", ACCESS_EVENT]
    accepted = _one(lines, "refund.accepted")
    assert (accepted.payment_id, accepted.amount, accepted.refunded_amount) == (
        str(payment.id),
        300,
        300,
    )
    changed = _one(lines, "payment.status_changed")
    assert (changed.from_status, changed.to_status) == ("captured", "partially_refunded")
    assert _one(lines, ACCESS_EVENT).status == 201


@pytest.mark.regression
@allure.title("A rejected transition is logged as a rejection and changes no status")
def test_a_rejected_transition_is_logged(
    api: PaymentsApi, payment_factory: PaymentFactory, app_log: AppLog
) -> None:
    payment = payment_factory.create(PaymentStatus.CREATED)
    response = api.capture(payment.id)
    assert response.status_code == 409

    lines = app_log.request(response.headers["X-Request-ID"])

    assert _events(lines) == ["payment.transition_rejected", ACCESS_EVENT]
    rejected = _one(lines, "payment.transition_rejected")
    assert (rejected.payment_id, rejected.action, rejected.from_status) == (
        str(payment.id),
        "capture",
        "created",
    )
    assert _one(lines, ACCESS_EVENT).status == 409


@pytest.mark.regression
@allure.title("A refund over the remainder is logged as rejected with the refundable amount")
def test_a_rejected_refund_is_logged(
    api: PaymentsApi, payment_factory: PaymentFactory, app_log: AppLog
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=1000)
    response = api.refund(payment.id, 1001)
    assert response.status_code == 422

    lines = app_log.request(response.headers["X-Request-ID"])

    assert _events(lines) == ["refund.rejected", ACCESS_EVENT]
    rejected = _one(lines, "refund.rejected")
    assert (rejected.amount, rejected.refundable, rejected.reason) == (
        1001,
        1000,
        "refund_exceeds_amount",
    )


@pytest.mark.smoke
@allure.title("No password, token, one-time code or card token appears in the log")
def test_no_secret_appears_in_the_log(
    settings: Settings, auth_api: AuthApi, merchant_factory: MerchantFactory, app_log: AppLog
) -> None:
    card_token = f"tok_{uuid4().hex}"  # unique, so it cannot be mistaken for another test's data
    merchant = merchant_factory.create("secrets")
    request_ids: list[str] = []

    admin_login = auth_api.login(settings.admin_email, settings.admin_password)
    request_ids.append(admin_login.headers["X-Request-ID"])
    mfa_token = admin_login.expect(200).mfa_token
    assert mfa_token
    code = totp_code(settings.admin_totp_secret)
    admin_session = auth_api.two_factor(mfa_token, code)
    request_ids.append(admin_session.headers["X-Request-ID"])
    admin_token = admin_session.expect(200).access_token

    payment = merchant.api.create(card_token=card_token)
    request_ids.append(payment.headers["X-Request-ID"])
    payment_id = payment.expect(201).id
    for step in (merchant.api.authorize, merchant.api.capture):
        request_ids.append(step(payment_id).headers["X-Request-ID"])
    request_ids.append(merchant.api.refund(payment_id, 100).headers["X-Request-ID"])

    # The scan is only meaningful if the requests above are really in the log.
    own_lines = [line for request_id in request_ids for line in app_log.request(request_id)]
    assert {"/auth/login", "/auth/2fa", "/payments"} <= {line.path for line in own_lines}
    assert {"payment.created", "refund.accepted"} <= {line.event for line in own_lines}

    log = app_log.text()
    secrets = {
        "merchant password": merchant.password,
        "merchant token": merchant.token,
        "admin password": settings.admin_password,
        "admin TOTP secret": settings.admin_totp_secret,
        "admin MFA token": mfa_token,
        "admin token": admin_token,
        "card token": card_token,
    }
    for name, value in secrets.items():
        assert value not in log, f"the {name} appears in the log"
    # Any JWT, from any test, and any Authorization header value.
    assert "eyJ" not in log, "a JWT appears in the log"
    assert "Bearer" not in log, "an Authorization header value appears in the log"
    # A 6-digit code is too short to search for in free text (digits occur in ids and
    # timestamps), so compare it with whole field values of this test's own lines.
    assert code not in {str(v) for line in own_lines for v in line.model_dump().values()}
