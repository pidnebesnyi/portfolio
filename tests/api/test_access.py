"""Basic access checks: who may call what, and what a caller must not learn."""

import secrets
from uuid import uuid4

import pytest

from tests.clients.http import LoggedHttpClient
from tests.clients.merchants_api import MerchantsApi
from tests.clients.payments_api import PaymentsApi
from tests.config import Settings
from tests.factories.merchant_factory import MerchantAccount
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.allure_links import area, requirement
from tests.utils.tokens import forge_token

pytestmark = [area("Basic access checks"), requirement("PAY-ACCESS")]


@pytest.mark.smoke
def test_expired_token_is_rejected(
    api: PaymentsApi, merchant: MerchantAccount, settings: Settings
) -> None:
    expired = forge_token(
        settings.jwt_secret, user_id=uuid4(), merchant_id=merchant.id, expires_in_s=-60
    )

    api.with_token(expired).list_payments().expect_error(401, "token_expired")


@pytest.mark.smoke
def test_merchant_cannot_read_another_merchants_payment(
    other_merchant: MerchantAccount, api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    mine = payment_factory.create()

    # 404, not 403: the response must not confirm that the payment exists.
    other_merchant.api.get(mine.id).expect_error(404, "payment_not_found")
    assert api.get(mine.id).expect(200).id == mine.id


@pytest.mark.regression
def test_request_without_token_is_unauthorized(api: PaymentsApi) -> None:
    anonymous = api.with_token(None)

    anonymous.list_payments().expect_error(401, "unauthorized")
    anonymous.create().expect_error(401, "unauthorized")


@pytest.mark.regression
@pytest.mark.parametrize("token", ["not-a-jwt", "a.b.c"], ids=["garbage", "malformed"])
def test_malformed_token_is_unauthorized(api: PaymentsApi, token: str) -> None:
    api.with_token(token).list_payments().expect_error(401, "invalid_token")


@pytest.mark.regression
def test_token_signed_with_another_secret_is_rejected(
    api: PaymentsApi, merchant: MerchantAccount
) -> None:
    forged = forge_token(secrets.token_hex(32), user_id=uuid4(), merchant_id=merchant.id)

    api.with_token(forged).list_payments().expect_error(401, "invalid_token")


@pytest.mark.regression
@pytest.mark.parametrize("action", ["authorize", "capture", "void", "refund"])
def test_merchant_cannot_act_on_another_merchants_payment(
    other_merchant: MerchantAccount,
    payment_factory: PaymentFactory,
    api: PaymentsApi,
    action: str,
) -> None:
    mine = payment_factory.create(PaymentStatus.CAPTURED)
    foreign = other_merchant.api

    if action == "refund":
        foreign.refund(mine.id, 1).expect_error(404, "payment_not_found")
    else:
        getattr(foreign, action)(mine.id).expect_error(404, "payment_not_found")

    assert api.get(mine.id).expect(200).status is PaymentStatus.CAPTURED


@pytest.mark.regression
def test_list_never_shows_other_merchants_payments(
    other_merchant: MerchantAccount, payment_factory: PaymentFactory
) -> None:
    payment_factory.create()

    assert other_merchant.api.list_payments().expect(200).total == 0


@pytest.mark.regression
def test_merchant_cannot_use_admin_endpoints(
    http: LoggedHttpClient, merchant: MerchantAccount
) -> None:
    MerchantsApi(http, merchant.token).list_raw().expect_error(403, "forbidden")


@pytest.mark.regression
def test_admin_token_cannot_use_merchant_endpoints(admin_token: str, api: PaymentsApi) -> None:
    api.with_token(admin_token).list_payments().expect_error(403, "forbidden")


@pytest.mark.regression
def test_admin_endpoints_require_a_token(http: LoggedHttpClient) -> None:
    MerchantsApi(http, None).list_raw().expect_error(401, "unauthorized")
