import re
from uuid import UUID

from playwright.sync_api import Page, expect

from tests.pages.base_page import BasePage


class PaymentDetailPage(BasePage):
    """/ui/payments/{id}: read-only facts plus the refund form (captured payments only)."""

    def __init__(self, page: Page, payment_id: UUID | None = None) -> None:
        super().__init__(page)
        self.path = f"/ui/payments/{payment_id}" if payment_id else ""
        self.id = page.get_by_test_id("payment-id")
        self.status = page.get_by_test_id("payment-status")
        self.amount = page.get_by_test_id("payment-amount")
        self.refunded = page.get_by_test_id("payment-refunded")
        self.description = page.get_by_test_id("payment-description")
        self.refund_form = page.get_by_test_id("refund-form")
        self.refund_amount = page.get_by_label("Refund amount")
        self.refund_submit = page.get_by_test_id("refund-submit")
        self.refund_unavailable = page.get_by_test_id("refund-unavailable")

    def expect_loaded(self) -> None:
        expect(self.page).to_have_url(re.compile(r"/ui/payments/[0-9a-f-]{36}$"))
        expect(self.id).to_be_visible()

    def refund(self, amount: int) -> None:
        self.refund_amount.fill(str(amount))
        self.refund_submit.click()
