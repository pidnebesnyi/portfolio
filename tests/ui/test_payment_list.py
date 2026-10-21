"""What the payment list shows: columns, order, formatting, the empty state and the cap."""

import re

import allure
import pytest
from playwright.sync_api import Page, expect

from tests.clients.payments_api import PaymentsApi
from tests.pages.payments_page import PaymentsPage
from tests.utils.allure_links import area, requirement

pytestmark = [pytest.mark.ui, area("UI payments"), requirement("PAY-LIST")]


@pytest.mark.regression
@allure.title("The list is a table with its columns and one row per payment, newest first")
def test_list_is_a_table_with_one_row_per_payment_newest_first(
    merchant_page: Page, api: PaymentsApi
) -> None:
    ids = [api.create(description=f"order {n}", amount=1000 + n).expect(201).id for n in range(3)]
    payments = PaymentsPage(merchant_page)

    payments.open()

    expect(payments.header_row).to_have_text(
        re.compile(r"^Created\s*Description\s*Amount\s*Status\s*$")
    )
    expect(payments.rows).to_have_count(3)
    shown = [row.get_attribute("data-testid") for row in payments.rows.all()]
    assert shown == [f"payment-row-{payment_id}" for payment_id in reversed(ids)]


@pytest.mark.regression
@allure.title("A row shows the description, the amount with its currency, and the status")
def test_row_shows_description_amount_and_status(merchant_page: Page, api: PaymentsApi) -> None:
    payment = api.create(description="order 42", amount=1050, currency="EUR").expect(201)
    payments = PaymentsPage(merchant_page)

    payments.open()

    row = payments.row(payment.id)
    expect(row).to_contain_text("order 42")
    expect(row).to_contain_text("10.50 EUR")
    expect(payments.status_of(payment.id)).to_have_text("created")
    expect(row.get_by_role("link", name="Details")).to_have_attribute(
        "href", f"/ui/payments/{payment.id}"
    )


@pytest.mark.regression
@allure.title("A merchant without payments sees the empty state and no table")
def test_merchant_without_payments_sees_the_empty_state(merchant_page: Page) -> None:
    payments = PaymentsPage(merchant_page)

    payments.open()

    payments.expect_total(0)
    expect(payments.empty_state).to_have_text("No payments match.")
    expect(payments.table).to_have_count(0)
    expect(payments.truncated).to_have_count(0)


@pytest.mark.regression
@allure.title("A description with markup is shown as text, not as markup")
def test_description_with_markup_is_shown_as_text(merchant_page: Page, api: PaymentsApi) -> None:
    text = "<b>bold</b> & <script>window.injected = true</script>"
    payment = api.create(description=text).expect(201)
    payments = PaymentsPage(merchant_page)

    payments.open()

    expect(payments.row(payment.id)).to_contain_text(text)
    assert merchant_page.evaluate("window.injected") is None
    expect(payments.row(payment.id).locator("b")).to_have_count(0)


@pytest.mark.regression
@allure.title("The list shows the newest 100 payments and says so when there are more")
def test_list_is_capped_at_100_rows_and_says_so(merchant_page: Page, api: PaymentsApi) -> None:
    for _ in range(101):
        api.create().expect(201)
    payments = PaymentsPage(merchant_page)

    payments.open()

    payments.expect_total(101)
    expect(payments.rows).to_have_count(100)
    expect(payments.truncated).to_have_text(
        "Showing the newest 100; narrow the filters to see the rest."
    )
