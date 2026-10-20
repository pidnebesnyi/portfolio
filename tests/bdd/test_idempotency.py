import allure
import pytest
from pytest_bdd import scenario

from tests.utils.allure_links import area, requirement

pytestmark = [area("Idempotency"), requirement("PAY-IDEMP")]


@pytest.mark.regression
@allure.title("Repeating a payment request returns the same payment")
@scenario("features/idempotency.feature", "Repeating a payment request returns the same payment")
def test_repeating_a_request_returns_the_same_payment() -> None:
    """Steps: tests/bdd/steps/idempotency.py"""
