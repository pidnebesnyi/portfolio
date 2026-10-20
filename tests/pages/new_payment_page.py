import allure
from playwright.sync_api import Page

from tests.pages.base_page import BasePage


class NewPaymentPage(BasePage):
    path = "/ui/payments/new"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.amount = page.get_by_label("Amount")
        self.currency = page.get_by_label("Currency")
        self.description = page.get_by_label("Description")
        self.card_token = page.get_by_label("Card token")
        self.submit = page.get_by_test_id("new-submit")

    def create(
        self,
        *,
        amount: str,
        currency: str = "UAH",
        description: str = "",
        card_token: str = "tok_success",
    ) -> None:
        with allure.step(f"Fill in and submit the new payment form: {amount} {currency}"):
            self.amount.fill(amount)
            self.currency.select_option(currency)
            self.description.fill(description)
            self.card_token.fill(card_token)
            self.submit.click()
