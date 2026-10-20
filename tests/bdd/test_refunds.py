import allure
import pytest
from pytest_bdd import scenario

from tests.utils.allure_links import area, requirement

pytestmark = [area("Refunds"), requirement("PAY-REFUND")]


@pytest.mark.regression
@allure.title("Refunds add up and never exceed the payment")
@scenario("features/refunds.feature", "Refunds add up and never exceed the payment")
def test_refunds_add_up_and_never_exceed_the_payment() -> None:
    """Steps: tests/bdd/steps/refunds.py"""
