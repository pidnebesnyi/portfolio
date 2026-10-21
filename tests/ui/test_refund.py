import allure
import pytest
from playwright.sync_api import Page, expect

from tests.clients.payments_api import PaymentsApi
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.pages.payment_detail_page import PaymentDetailPage
from tests.utils.aaa import act, arrange, check
from tests.utils.allure_links import area, requirement

pytestmark = [pytest.mark.ui, area("UI refunds"), requirement("PAY-REFUND")]

AMOUNT = 2000  # 20.00


@pytest.mark.smoke
@allure.title("A merchant refunds a captured payment in two steps")
def test_merchant_refunds_a_captured_payment_in_two_steps(
    merchant_page: Page, api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    with arrange("a captured payment of 20.00 open in the browser"):
        payment = payment_factory.create(PaymentStatus.CAPTURED, amount=AMOUNT)
        detail = PaymentDetailPage(merchant_page, payment.id)
        detail.open()

    with act("refund 5.00"):
        detail.refund(500)

    with check("the page shows a partial refund of 5.00"):
        expect(detail.flash_success).to_have_text("Refund created")
        expect(detail.status).to_have_text("partially_refunded")
        expect(detail.refunded).to_have_text("5.00 UAH")

    with act("refund the remaining 15.00"):
        detail.refund(1500)

    with check("the page shows a full refund, offers no form, and the API agrees"):
        expect(detail.status).to_have_text("refunded")
        expect(detail.refunded).to_have_text("20.00 UAH")
        expect(detail.refund_form).to_have_count(0)
        expect(detail.refund_unavailable).to_be_visible()
        stored = api.get(payment.id).expect(200)
        assert (stored.status, stored.refunded_amount) == (PaymentStatus.REFUNDED, AMOUNT)


@pytest.mark.regression
@allure.title("A refund over the remaining amount is refused and changes nothing")
def test_refund_over_the_remaining_amount_is_refused_and_changes_nothing(
    merchant_page: Page, api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    with arrange("a captured payment of 20.00 open in the browser"):
        payment = payment_factory.create(PaymentStatus.CAPTURED, amount=AMOUNT)
        detail = PaymentDetailPage(merchant_page, payment.id)
        detail.open()

    with act("refund 20.01, one cent over the payment"):
        detail.refund(AMOUNT + 1)

    with check("the page shows the error and the payment is unchanged"):
        expect(detail.flash_error).to_contain_text("exceeds")
        expect(detail.status).to_have_text("captured")
        stored = api.get(payment.id).expect(200)
        assert (stored.status, stored.refunded_amount) == (PaymentStatus.CAPTURED, 0)


@pytest.mark.regression
@pytest.mark.parametrize("status", [PaymentStatus.CREATED, PaymentStatus.AUTHORIZED])
@allure.title("A payment in the {status} state offers no refund form")
def test_payments_that_are_not_captured_offer_no_refund_form(
    merchant_page: Page, payment_factory: PaymentFactory, status: PaymentStatus
) -> None:
    payment = payment_factory.create(status)
    detail = PaymentDetailPage(merchant_page, payment.id)

    detail.open()

    expect(detail.status).to_have_text(status.value)
    expect(detail.refund_form).to_have_count(0)
    expect(detail.refund_unavailable).to_be_visible()


@pytest.mark.regression
@pytest.mark.parametrize("amount", ["abc", "0", "-1", "1.5"])
@allure.title("A refund amount that is not a whole positive number is refused: '{amount}'")
def test_refund_amount_that_is_not_a_whole_positive_number_is_refused(
    merchant_page: Page, api: PaymentsApi, payment_factory: PaymentFactory, amount: str
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=AMOUNT)
    detail = PaymentDetailPage(merchant_page, payment.id)
    detail.open()

    detail.refund_amount.fill(amount)
    detail.refund_submit.click()

    expect(detail.flash_error).to_have_text("Enter the refund amount in minor units")
    expect(detail.status).to_have_text("captured")
    assert api.get(payment.id).expect(200).refunded_amount == 0


@pytest.mark.regression
@allure.title("The refund form says how much is still refundable")
def test_refund_form_says_how_much_is_still_refundable(
    merchant_page: Page, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=AMOUNT)
    detail = PaymentDetailPage(merchant_page, payment.id)
    detail.open()
    expect(detail.refund_form).to_contain_text(f"up to {AMOUNT}")

    detail.refund(500)

    expect(detail.refund_form).to_contain_text(f"up to {AMOUNT - 500}")
    expect(detail.refund_amount).to_have_value("")


@pytest.mark.regression
@allure.title("The refund form can be submitted with the Enter key")
def test_refund_form_can_be_submitted_with_the_enter_key(
    merchant_page: Page, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=AMOUNT)
    detail = PaymentDetailPage(merchant_page, payment.id)
    detail.open()

    detail.refund_amount.fill("250")
    detail.refund_amount.press("Enter")

    expect(detail.flash_success).to_have_text("Refund created")
    expect(detail.refunded).to_have_text("2.50 UAH")


@pytest.mark.regression
@allure.title("Refunding to the last cent hides the form and keeps the history readable")
def test_refunding_to_the_last_cent_hides_the_form(
    merchant_page: Page, api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=3)
    detail = PaymentDetailPage(merchant_page, payment.id)
    detail.open()

    for _ in range(3):
        detail.refund(1)
        expect(detail.flash_success).to_have_text("Refund created")

    expect(detail.status).to_have_text("refunded")
    expect(detail.refunded).to_have_text("0.03 UAH")
    expect(detail.refund_form).to_have_count(0)
    assert api.get(payment.id).expect(200).refunded_amount == 3
