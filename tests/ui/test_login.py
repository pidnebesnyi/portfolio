import re

import pytest
from playwright.sync_api import BrowserContext, Page, expect

from tests.config import Settings
from tests.factories.merchant_factory import MerchantAccount
from tests.pages.admin_page import AdminPage
from tests.pages.login_page import LoginPage, TwoFactorPage
from tests.pages.payments_page import PaymentsPage
from tests.utils.allure_links import area, requirement
from tests.utils.tokens import totp_code

# `sensitive`: these tests type credentials, so their trace and video are discarded on failure.
pytestmark = [pytest.mark.ui, pytest.mark.sensitive, area("UI login"), requirement("AUTH-UI")]


@pytest.mark.smoke
def test_merchant_logs_in_with_email_and_password(page: Page, merchant: MerchantAccount) -> None:
    login = LoginPage(page)
    login.open()

    login.log_in(merchant.email, merchant.password)

    payments = PaymentsPage(page)
    payments.expect_loaded()
    expect(payments.role_badge).to_have_text("merchant")
    payments.expect_total(0)


@pytest.mark.smoke
def test_admin_logs_in_with_password_and_totp(
    page: Page, settings: Settings, merchant: MerchantAccount
) -> None:
    login = LoginPage(page)
    login.open()

    login.log_in(settings.admin_email, settings.admin_password)
    two_factor = TwoFactorPage(page)
    two_factor.expect_loaded()
    two_factor.verify(totp_code(settings.admin_totp_secret))

    admin = AdminPage(page)
    admin.expect_loaded()
    expect(admin.role_badge).to_have_text("admin")
    # The merchant was created through the API a moment ago and is listed for the admin.
    expect(admin.merchant_row(merchant.id)).to_contain_text(merchant.email)


@pytest.mark.regression
def test_wrong_password_is_rejected_without_revealing_which_part_was_wrong(
    page: Page, merchant: MerchantAccount
) -> None:
    login = LoginPage(page)
    login.open()

    login.log_in(merchant.email, merchant.password + "x")

    login.expect_loaded()
    expect(login.flash_error).to_have_text("Invalid email or password")
    expect(login.role_badge).to_have_count(0)


@pytest.mark.regression
def test_wrong_totp_code_keeps_the_admin_on_the_verification_step(
    page: Page, settings: Settings
) -> None:
    login = LoginPage(page)
    login.open()
    login.log_in(settings.admin_email, settings.admin_password)
    two_factor = TwoFactorPage(page)
    two_factor.expect_loaded()

    # A code that cannot be valid in the current, previous or next 30 s window.
    two_factor.verify("00000" + ("1" if totp_code(settings.admin_totp_secret) != "000001" else "2"))

    two_factor.expect_loaded()
    expect(two_factor.flash_error).to_have_text("Wrong verification code")


@pytest.mark.regression
def test_session_cookie_is_http_only_and_same_site_lax(
    page: Page, context: BrowserContext, merchant: MerchantAccount
) -> None:
    login = LoginPage(page)
    login.open()
    login.log_in(merchant.email, merchant.password)
    PaymentsPage(page).expect_loaded()

    (cookie,) = (c for c in context.cookies() if c["name"] == "session")

    assert cookie.get("httpOnly") is True
    assert cookie.get("sameSite") == "Lax"
    # JavaScript cannot read it: the page's own document.cookie does not contain it.
    assert "session=" not in page.evaluate("document.cookie")


@pytest.mark.regression
def test_logging_out_ends_the_session(merchant_page: Page) -> None:
    payments = PaymentsPage(merchant_page)
    payments.open()

    payments.log_out()

    LoginPage(merchant_page).expect_loaded()
    merchant_page.goto(PaymentsPage.path)
    expect(merchant_page).to_have_url(re.compile(r"/ui/login$"))


@pytest.mark.regression
@pytest.mark.parametrize("path", ["/ui/payments", "/ui/payments/new"])
def test_protected_pages_redirect_anonymous_visitors_to_login(page: Page, path: str) -> None:
    page.goto(path)

    LoginPage(page).expect_loaded()
