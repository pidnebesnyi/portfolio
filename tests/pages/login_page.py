import re

from playwright.sync_api import Page, expect

from tests.pages.base_page import BasePage
from tests.utils.aaa import page_action


class LoginPage(BasePage):
    path = "/ui/login"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.email = page.get_by_label("Email")
        self.password = page.get_by_label("Password")
        self.submit = page.get_by_test_id("login-submit")

    @page_action("log in as {email}")
    def log_in(self, email: str, password: str) -> None:
        self.email.fill(email)
        self.password.fill(password)
        self.submit.click()


class TwoFactorPage(BasePage):
    path = "/ui/2fa"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.code = page.get_by_label("Code")
        self.submit = page.get_by_test_id("2fa-submit")

    def expect_loaded(self) -> None:
        expect(self.page).to_have_url(re.compile(r"/ui/2fa$"))
        expect(self.code).to_be_visible()

    @page_action("submit the one-time code")
    def verify(self, code: str) -> None:
        self.code.fill(code)
        self.submit.click()
