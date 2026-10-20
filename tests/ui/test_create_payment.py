from uuid import UUID

import allure
import pytest
from playwright.sync_api import Page, expect

from tests.clients.payments_api import PaymentsApi
from tests.models.payments import PaymentStatus
from tests.pages.new_payment_page import NewPaymentPage
from tests.pages.payment_detail_page import PaymentDetailPage
from tests.utils.allure_links import area, requirement

pytestmark = [pytest.mark.ui, area("UI payments"), requirement("PAY-CREATE")]


@pytest.mark.smoke
@allure.title("A merchant creates a payment through the form")
def test_merchant_creates_a_payment_through_the_form(merchant_page: Page, api: PaymentsApi) -> None:
    form = NewPaymentPage(merchant_page)
    form.open()

    form.create(amount="1050", currency="USD", description="order 42")

    detail = PaymentDetailPage(merchant_page)
    detail.expect_loaded()
    expect(detail.flash_success).to_have_text("Payment created")
    expect(detail.status).to_have_text("created")
    expect(detail.amount).to_have_text("10.50 USD")
    expect(detail.description).to_have_text("order 42")
    # The UI is only the front: the API (and so the database) holds exactly this payment.
    stored = api.list_payments().expect(200)
    assert stored.total == 1
    payment = stored.items[0]
    assert payment.id == UUID(detail.id.inner_text())
    assert (payment.amount, payment.currency, payment.status) == (
        1050,
        "USD",
        PaymentStatus.CREATED,
    )


@pytest.mark.regression
@pytest.mark.parametrize("amount", ["abc", "0", "-5", "10.5"])
@allure.title("Invalid amount '{amount}' is rejected and nothing is created")
def test_invalid_amount_is_rejected_and_nothing_is_created(
    merchant_page: Page, api: PaymentsApi, amount: str
) -> None:
    form = NewPaymentPage(merchant_page)
    form.open()

    form.create(amount=amount)

    form.expect_loaded()
    expect(form.flash_error).to_be_visible()
    assert api.list_payments().expect(200).total == 0
