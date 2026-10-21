"""Paging and filters at their edges."""

from datetime import UTC, datetime, timedelta

import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.allure_links import area, requirement

pytestmark = [area("Payments"), requirement("PAY-LIST")]


@pytest.mark.regression
@allure.title("The default page holds 20 payments and the total counts them all")
def test_default_page_holds_twenty_payments(api: PaymentsApi) -> None:
    for _ in range(23):
        api.create().expect(201)

    page = api.list_payments().expect(200)

    assert (len(page.items), page.total, page.limit, page.offset) == (20, 23, 20, 0)


@pytest.mark.regression
@allure.title("An offset past the end gives an empty page that still reports the total")
def test_offset_past_the_end_gives_an_empty_page(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment_factory.create()
    payment_factory.create()

    page = api.list_payments(offset=50).expect(200)

    assert (page.items, page.total, page.offset) == ([], 2, 50)


@pytest.mark.regression
@allure.title("The largest page size is accepted")
def test_largest_page_size_is_accepted(api: PaymentsApi, payment_factory: PaymentFactory) -> None:
    payment_factory.create()

    page = api.list_payments(limit=100).expect(200)

    assert (page.limit, len(page.items)) == (100, 1)


@pytest.mark.regression
@allure.title("A date range that ends before it starts matches nothing")
def test_reversed_date_range_matches_nothing(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment_factory.create()
    now = datetime.now(UTC)

    page = api.list_payments(
        created_from=now + timedelta(hours=1), created_to=now - timedelta(hours=1)
    ).expect(200)

    assert (page.items, page.total) == ([], 0)


@pytest.mark.regression
@allure.title("Status and date filters combine")
def test_status_and_date_filters_combine(api: PaymentsApi, payment_factory: PaymentFactory) -> None:
    captured = payment_factory.create(PaymentStatus.CAPTURED)
    payment_factory.create()
    now = datetime.now(UTC)

    page = api.list_payments(
        status=PaymentStatus.CAPTURED,
        created_from=now - timedelta(hours=1),
        created_to=now + timedelta(hours=1),
    ).expect(200)

    assert [p.id for p in page.items] == [captured.id]


@pytest.mark.regression
@pytest.mark.parametrize(
    "params",
    [{"created_from": "yesterday"}, {"created_to": "2026-13-45"}, {"limit": "many"}],
    ids=["text-date", "impossible-date", "text-limit"],
)
@allure.title("The list rejects a value of the wrong kind: {param_id}")
def test_list_rejects_a_value_of_the_wrong_kind(
    api: PaymentsApi, params: dict[str, object]
) -> None:
    api.list_raw(params).expect_error(422, "validation_error")
