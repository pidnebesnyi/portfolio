"""Fonts and colours of key elements, read with getComputedStyle and compared with the values
the stylesheet defines (tests/ui/design_tokens.py). What is checked is the browser's final
answer, so a rule that never applies (typo, overridden, wrong selector) fails here though the CSS
looks right. Checks are soft (tests/utils/soft_checks.py): every mismatch of a test is collected,
with a screenshot of the outlined element, and `soft_styles.verify()` fails the test once with
all of them."""

import allure
import pytest
from playwright.sync_api import Page

from tests.factories.merchant_factory import MerchantAccount
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.pages.login_page import LoginPage
from tests.pages.new_payment_page import NewPaymentPage
from tests.pages.payment_detail_page import PaymentDetailPage
from tests.pages.payments_page import PaymentsPage
from tests.ui import design_tokens as tokens
from tests.utils.allure_links import area, requirement
from tests.utils.soft_checks import StyleCollector

pytestmark = [pytest.mark.ui, area("UI look"), requirement("UI-STYLE")]


@pytest.mark.smoke
@allure.title("The login page uses the body font, the heading size and block labels")
def test_login_page_uses_the_body_font_the_heading_size_and_block_labels(
    page: Page, soft_styles: StyleCollector
) -> None:
    login = LoginPage(page)
    login.open()

    soft_styles.check(page.locator("body"), tokens.BODY)
    soft_styles.check(page.get_by_role("heading", level=1), tokens.HEADING_1)
    soft_styles.check(page.get_by_text("Email", exact=True), tokens.LABEL)  # the <label>
    soft_styles.verify()


@pytest.mark.regression
@allure.title("The payments table uses the divider colour and cell padding")
def test_payments_table_uses_the_divider_colour_and_cell_padding(
    merchant_page: Page, payment_factory: PaymentFactory, soft_styles: StyleCollector
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED)
    payments = PaymentsPage(merchant_page)

    payments.open()

    soft_styles.check(payments.header, tokens.HEADER_RULE)
    # Playwright 1.49 reports a <th> without a scope attribute as a plain cell.
    soft_styles.check(
        merchant_page.get_by_role("cell", name="Status", exact=True), tokens.TABLE_CELL
    )
    soft_styles.check(payments.status_of(payment.id), {**tokens.TABLE_CELL, **tokens.BODY_TEXT})
    soft_styles.verify()


@pytest.mark.regression
@pytest.mark.sensitive
@allure.title("An error message has a red border")
def test_error_message_has_a_red_border(
    page: Page, merchant: MerchantAccount, soft_styles: StyleCollector
) -> None:
    login = LoginPage(page)
    login.open()

    login.log_in(merchant.email, merchant.password + "x")

    soft_styles.check(login.flash_error, tokens.FLASH_ERROR_BORDER)
    soft_styles.verify()


@pytest.mark.regression
@allure.title("A success message has a green border")
def test_success_message_has_a_green_border(
    merchant_page: Page, soft_styles: StyleCollector
) -> None:
    form = NewPaymentPage(merchant_page)
    form.open()

    form.create(amount="500")

    soft_styles.check(PaymentDetailPage(merchant_page).flash_success, tokens.FLASH_SUCCESS_BORDER)
    soft_styles.verify()


@pytest.mark.regression
@allure.title("The refresh error is styled as an error message")
def test_refresh_error_is_styled_as_an_error_message(
    merchant_page: Page, payment_factory: PaymentFactory, soft_styles: StyleCollector
) -> None:
    payment = payment_factory.create()
    detail = PaymentDetailPage(merchant_page, payment.id)
    detail.open()
    merchant_page.route("**/status", lambda route: route.fulfill(status=500, json={}))

    detail.refresh_status()

    soft_styles.check(detail.refresh_error, tokens.FLASH_ERROR_BORDER)
    soft_styles.verify()
