"""Parts every screen shares: the header, navigation and flash messages.

Page objects expose locators and intent-level actions; assertions about the product stay in the
tests, except `expect_*` helpers that wait for a page to be ready (auto-waiting, no sleeps).
Locators use get_by_role / get_by_label / get_by_test_id only.
"""

import re

import allure
from playwright.sync_api import Locator, Page, expect


class BasePage:
    path: str  # set by subclasses that have a fixed URL

    def __init__(self, page: Page) -> None:
        self.page = page
        self.header = page.get_by_test_id("header")
        self.role_badge = page.get_by_test_id("user-role")
        self.logout_button = page.get_by_test_id("logout")
        self.payments_link = page.get_by_test_id("nav-payments")
        self.new_payment_link = page.get_by_test_id("nav-new-payment")
        self.flash_success = page.get_by_test_id("flash-success")
        self.flash_error = page.get_by_test_id("flash-error")

    def open(self) -> None:
        with allure.step(f"Open {self.path}"):
            self.page.goto(self.path)
            self.expect_loaded()

    def expect_loaded(self) -> None:
        """The URL is this page's (ignoring any query string) and the page has rendered."""
        expect(self.page).to_have_url(re.compile(re.escape(self.path) + r"(\?.*)?$"))
        expect(self.page.get_by_role("heading", level=1)).to_be_visible()

    def flash(self, level: str) -> Locator:
        return self.page.get_by_test_id(f"flash-{level}")

    @allure.step("Log out")
    def log_out(self) -> None:
        self.logout_button.click()
