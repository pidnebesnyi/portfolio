"""What the API lists for a merchant must be what the database holds, field by field."""

from typing import Any

import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.db.checks import assert_no_diff
from tests.factories.merchant_factory import MerchantAccount
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.allure_links import area, requirement
from tests.utils.db import Database
from tests.utils.payment_compare import (
    PAYMENT_COLUMNS,
    diff_payments,
    normalize_api,
    normalize_db,
)

pytestmark = [pytest.mark.regression, pytest.mark.db, area("Database consistency")]

# One payment per state, in different currencies and amounts. A page of 3 over 7 payments
# forces the listing to be followed across three pages.
PAYMENTS = [
    (PaymentStatus.CREATED, 1050, "UAH"),
    (PaymentStatus.AUTHORIZED, 2500, "USD"),
    (PaymentStatus.CAPTURED, 99999, "EUR"),
    (PaymentStatus.PARTIALLY_REFUNDED, 4000, "UAH"),
    (PaymentStatus.REFUNDED, 1234, "USD"),
    (PaymentStatus.VOIDED, 777, "EUR"),
    (PaymentStatus.FAILED, 1, "UAH"),
]
PAGE_SIZE = 3


def list_every_page(api: PaymentsApi) -> tuple[list[dict[str, Any]], int]:
    """The raw JSON items of all pages and the `total` the API reported."""
    items: list[dict[str, Any]] = []
    while True:
        response = api.list_payments(limit=PAGE_SIZE, offset=len(items))
        page = response.expect(200)  # validated against the model; normalization gets the raw JSON
        body = response.raw.json()
        items += body["items"]
        if not body["items"] or len(items) >= page.total:
            return items, page.total


@requirement("PAY-LIST")
@allure.title("The API's payment list equals the database rows")
def test_api_payment_list_equals_the_database_rows(
    api: PaymentsApi, db: Database, merchant: MerchantAccount, payment_factory: PaymentFactory
) -> None:
    for status, amount, currency in PAYMENTS:
        payment_factory.create(status, amount=amount, currency=currency)

    items, total = list_every_page(api)
    rows = db.fetch_all(
        f"SELECT {', '.join(PAYMENT_COLUMNS)} FROM payments WHERE merchant_id = %s",
        (merchant.id,),
    )

    assert_no_diff(diff_payments(normalize_api(items, total), normalize_db(rows)))
