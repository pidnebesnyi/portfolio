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


@pytest.mark.regression
@allure.title("The form offers the supported currencies and a ready card token")
def test_form_offers_the_supported_currencies_and_a_ready_card_token(merchant_page: Page) -> None:
    form = NewPaymentPage(merchant_page)

    form.open()

    expect(form.currency.locator("option")).to_have_text(["UAH", "USD", "EUR"])
    expect(form.currency).to_have_value("UAH")
    expect(form.card_token).to_have_value("tok_success")
    expect(form.amount).to_have_value("")
    expect(form.amount).to_be_editable()
    expect(form.submit).to_be_enabled()


@pytest.mark.regression
@allure.title("The success notice is shown once and gone after a reload")
def test_success_notice_is_shown_once(merchant_page: Page) -> None:
    form = NewPaymentPage(merchant_page)
    form.open()
    form.create(amount="500")
    detail = PaymentDetailPage(merchant_page)
    expect(detail.flash_success).to_have_text("Payment created")

    merchant_page.reload()

    detail.expect_loaded()
    expect(detail.flash_success).to_have_count(0)


@pytest.mark.regression
@requirement("PAY-IDEMP")
@allure.title("Submitting the same form twice creates one payment")
def test_submitting_the_same_form_twice_creates_one_payment(
    merchant_page: Page, api: PaymentsApi
) -> None:
    form = NewPaymentPage(merchant_page)
    form.open()
    key = form.idempotency_key()
    fields = {
        "amount": "700",
        "currency": "UAH",
        "description": "double click",
        "card_token": "tok_success",
        "idempotency_key": key,
    }

    # What a double click or a resubmit after a slow answer sends: the same form, twice.
    for _ in range(2):
        merchant_page.request.post("/ui/payments/new", form=fields)

    stored = api.list_payments().expect(200)
    assert [(p.description, p.amount) for p in stored.items] == [("double click", 700)]


@pytest.mark.regression
@requirement("PAY-IDEMP")
@allure.title("Each rendered form carries its own idempotency key")
def test_each_rendered_form_carries_its_own_idempotency_key(merchant_page: Page) -> None:
    form = NewPaymentPage(merchant_page)
    form.open()
    first = form.idempotency_key()

    form.open()

    assert form.idempotency_key() != first


@pytest.mark.regression
@allure.title("The description field stops at 255 characters")
def test_description_field_stops_at_255_characters(merchant_page: Page, api: PaymentsApi) -> None:
    form = NewPaymentPage(merchant_page)
    form.open()

    form.create(amount="500", description="d" * 300)

    detail = PaymentDetailPage(merchant_page)
    detail.expect_loaded()
    expect(detail.description).to_have_text("d" * 255)
    assert len(api.list_payments().expect(200).items[0].description) == 255
