import re
from uuid import UUID

import allure
from playwright.sync_api import Locator, Page, expect

from tests.pages.base_page import BasePage


class PaymentsPage(BasePage):
    """Merchant landing page: payment list with status and date filters."""

    path = "/ui/payments"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.status_filter = page.get_by_label("Status")
        self.from_filter = page.get_by_label("Created from")
        self.to_filter = page.get_by_label("Created to")
        self.apply_filter = page.get_by_test_id("filter-apply")
        self.reset_filter = page.get_by_test_id("filter-reset")
        self.total = page.get_by_test_id("payments-total")
        self.empty_state = page.get_by_test_id("payments-empty")

    def row(self, payment_id: UUID) -> Locator:
        return self.page.get_by_test_id(f"payment-row-{payment_id}")

    def status_of(self, payment_id: UUID) -> Locator:
        return self.page.get_by_test_id(f"payment-status-{payment_id}")

    def filter_by(
        self, *, status: str | None = None, created_from: str = "", created_to: str = ""
    ) -> None:
        """Dates are YYYY-MM-DD (UTC days, as the API stores them)."""
        title = f"Filter the list: status={status or 'any'}, from={created_from}, to={created_to}"
        with allure.step(title):
            self.status_filter.select_option(status or "")
            self.from_filter.fill(created_from)
            self.to_filter.fill(created_to)
            self.apply_filter.click()

    @allure.step("Expect the list total to be {count}")
    def expect_total(self, count: int) -> None:
        expect(self.total).to_have_text(f"Total: {count}")

    @allure.step("Open payment {payment_id} from the list")
    def open_payment(self, payment_id: UUID) -> None:
        self.page.get_by_test_id(f"payment-link-{payment_id}").click()
        expect(self.page).to_have_url(re.compile(rf"/ui/payments/{payment_id}$"))
