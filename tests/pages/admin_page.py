from uuid import UUID

from playwright.sync_api import Locator

from tests.pages.base_page import BasePage


class AdminPage(BasePage):
    """What an admin sees at /ui/payments: the merchant list."""

    path = "/ui/payments"

    def merchant_row(self, merchant_id: UUID) -> Locator:
        return self.page.get_by_test_id(f"merchant-row-{merchant_id}")
