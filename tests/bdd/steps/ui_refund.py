from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.common import Scene, minor_units
from tests.pages.payment_detail_page import PaymentDetailPage


@given("the merchant has the payment page open", target_fixture="detail")
def the_payment_page_is_open(scene: Scene, merchant_page: Page) -> PaymentDetailPage:
    detail = PaymentDetailPage(merchant_page, scene.payment_id)
    detail.open()
    return detail


@when(parsers.parse("the merchant refunds {amount} UAH on the page"))
def refund_on_the_page(detail: PaymentDetailPage, amount: str) -> None:
    detail.refund(minor_units(amount))


@then(parsers.parse("the page shows the payment as {status} with {amount} UAH refunded"))
def the_page_shows(detail: PaymentDetailPage, status: str, amount: str) -> None:
    expect(detail.status).to_have_text(status)
    expect(detail.refunded).to_have_text(f"{amount} UAH")
