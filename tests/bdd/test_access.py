import allure
import pytest
from pytest_bdd import scenario

from tests.utils.allure_links import area, requirement

pytestmark = [area("Basic access checks"), requirement("PAY-ACCESS")]


@pytest.mark.regression
@allure.title("Another merchant cannot see my payment")
@scenario("features/access.feature", "Another merchant cannot see my payment")
def test_another_merchant_cannot_see_my_payment() -> None:
    """Steps: tests/bdd/steps/access.py"""
