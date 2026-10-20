import pytest
from playwright.sync_api import Page, expect

from tests.clients.payments_api import PaymentsApi
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.pages.payment_detail_page import PaymentDetailPage
from tests.utils.allure_links import area, requirement

pytestmark = [pytest.mark.ui, area("UI refunds"), requirement("PAY-REFUND")]

AMOUNT = 2000  # 20.00


@pytest.mark.smoke
def test_merchant_refunds_a_captured_payment_in_two_steps(
    merchant_page: Page, api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=AMOUNT)
    detail = PaymentDetailPage(merchant_page, payment.id)
    detail.open()
    expect(detail.status).to_have_text("captured")

    detail.refund(500)

    expect(detail.flash_success).to_have_text("Refund created")
    expect(detail.status).to_have_text("partially_refunded")
    expect(detail.refunded).to_have_text("5.00 UAH")

    detail.refund(1500)

    expect(detail.status).to_have_text("refunded")
    expect(detail.refunded).to_have_text("20.00 UAH")
    expect(detail.refund_form).to_have_count(0)
    expect(detail.refund_unavailable).to_be_visible()
    stored = api.get(payment.id).expect(200)
    assert (stored.status, stored.refunded_amount) == (PaymentStatus.REFUNDED, AMOUNT)


@pytest.mark.regression
def test_refund_over_the_remaining_amount_is_refused_and_changes_nothing(
    merchant_page: Page, api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=AMOUNT)
    detail = PaymentDetailPage(merchant_page, payment.id)
    detail.open()

    detail.refund(AMOUNT + 1)

    expect(detail.flash_error).to_contain_text("exceeds")
    expect(detail.status).to_have_text("captured")
    stored = api.get(payment.id).expect(200)
    assert (stored.status, stored.refunded_amount) == (PaymentStatus.CAPTURED, 0)


@pytest.mark.regression
@pytest.mark.parametrize("status", [PaymentStatus.CREATED, PaymentStatus.AUTHORIZED])
def test_payments_that_are_not_captured_offer_no_refund_form(
    merchant_page: Page, payment_factory: PaymentFactory, status: PaymentStatus
) -> None:
    payment = payment_factory.create(status)
    detail = PaymentDetailPage(merchant_page, payment.id)

    detail.open()

    expect(detail.status).to_have_text(status.value)
    expect(detail.refund_form).to_have_count(0)
    expect(detail.refund_unavailable).to_be_visible()
