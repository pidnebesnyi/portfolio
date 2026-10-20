import allure
import pytest
from pytest_bdd import scenario

from tests.utils.allure_links import area, requirement

pytestmark = [area("UI refunds"), requirement("PAY-REFUND")]


@pytest.mark.regression
@allure.title("A merchant refunds part of a payment on its page")
@scenario("features/ui_refund.feature", "A merchant refunds part of a payment on its page")
def test_merchant_refunds_part_of_a_payment_on_its_page() -> None:
    """Steps: tests/bdd/steps/ui_refund.py"""
