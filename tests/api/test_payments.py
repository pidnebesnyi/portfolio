from datetime import UTC, datetime, timedelta

import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.factories.merchant_factory import MerchantAccount
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.allure_links import area, requirement

pytestmark = area("Payments")


@pytest.mark.smoke
@requirement("PAY-CREATE")
@allure.title("Creating a payment returns the created payment")
def test_create_payment_returns_created_payment(
    api: PaymentsApi, merchant: MerchantAccount
) -> None:
    payment = api.create(amount=1050, currency="USD", description="order 42").expect(201)

    assert payment.status is PaymentStatus.CREATED
    assert (payment.amount, payment.currency, payment.description) == (1050, "USD", "order 42")
    assert payment.merchant_id == merchant.id
    assert payment.refunded_amount == 0
    assert payment.failure_reason is None
    assert api.get(payment.id).expect(200) == payment


@pytest.mark.regression
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"amount": 0, "currency": "UAH", "card_token": "t"}, id="zero-amount"),
        pytest.param({"amount": -5, "currency": "UAH", "card_token": "t"}, id="negative-amount"),
        pytest.param(
            {"amount": 10.5, "currency": "UAH", "card_token": "t"}, id="fractional-amount"
        ),
        pytest.param({"amount": "10", "currency": "UAH", "card_token": "t"}, id="string-amount"),
        pytest.param(
            {"amount": 100, "currency": "GBP", "card_token": "t"}, id="unsupported-currency"
        ),
        pytest.param({"amount": 100, "card_token": "t"}, id="missing-currency"),
        pytest.param({"amount": 100, "currency": "UAH"}, id="missing-card-token"),
        pytest.param({"currency": "UAH", "card_token": "t"}, id="missing-amount"),
    ],
)
@requirement("PAY-CREATE")
@allure.title("Payment creation rejects an invalid body: {param_id}")
def test_create_payment_rejects_invalid_body(api: PaymentsApi, body: dict[str, object]) -> None:
    api.create_raw(body).expect_error(422, "validation_error")


@pytest.mark.regression
@requirement("PAY-LIST")
@allure.title("The list returns only own payments, newest first")
def test_list_returns_only_own_payments_newest_first(
    api: PaymentsApi, other_merchant: MerchantAccount, payment_factory: PaymentFactory
) -> None:
    first = payment_factory.create()
    second = payment_factory.create()
    other_merchant.api.create().expect(201)

    page = api.list_payments().expect(200)

    assert page.total == 2
    assert [p.id for p in page.items] == [second.id, first.id]


@pytest.mark.regression
@requirement("PAY-LIST")
@allure.title("The list filters by status")
def test_list_filters_by_status(api: PaymentsApi, payment_factory: PaymentFactory) -> None:
    created = payment_factory.create()
    captured = payment_factory.create(PaymentStatus.CAPTURED)

    only_captured = api.list_payments(status=PaymentStatus.CAPTURED).expect(200)
    only_created = api.list_payments(status=PaymentStatus.CREATED).expect(200)

    assert [p.id for p in only_captured.items] == [captured.id]
    assert [p.id for p in only_created.items] == [created.id]


@pytest.mark.regression
@requirement("PAY-LIST")
@allure.title("The list filters by created date range")
def test_list_filters_by_created_date_range(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create()
    now = datetime.now(UTC)

    inside = api.list_payments(
        created_from=now - timedelta(hours=1), created_to=now + timedelta(hours=1)
    ).expect(200)
    in_the_past = api.list_payments(created_to=now - timedelta(hours=1)).expect(200)
    in_the_future = api.list_payments(created_from=now + timedelta(hours=1)).expect(200)

    assert [p.id for p in inside.items] == [payment.id]
    assert in_the_past.total == 0
    assert in_the_future.total == 0


@pytest.mark.regression
@requirement("PAY-LIST")
@allure.title("The list paginates without overlap")
def test_list_paginates_without_overlap(api: PaymentsApi, payment_factory: PaymentFactory) -> None:
    created = [payment_factory.create().id for _ in range(3)]

    page_one = api.list_payments(limit=2, offset=0).expect(200)
    page_two = api.list_payments(limit=2, offset=2).expect(200)

    assert page_one.total == page_two.total == 3
    assert [p.id for p in page_one.items + page_two.items] == created[::-1]


@pytest.mark.regression
@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "bogus"}],
    ids=["limit-zero", "limit-too-big", "negative-offset", "unknown-status"],
)
@requirement("PAY-LIST")
@allure.title("The list rejects an invalid query: {param_id}")
def test_list_rejects_invalid_query(api: PaymentsApi, params: dict[str, object]) -> None:
    api.list_raw(params).expect_error(422, "validation_error")
