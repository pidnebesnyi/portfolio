import allure
import pytest
from pytest_bdd import scenario

from tests.utils.allure_links import area, requirement

pytestmark = [area("Provider integration"), requirement("PAY-PROVIDER")]


@pytest.mark.regression
@allure.title("A declined card ends the payment as failed with a reason")
@scenario("features/provider.feature", "A declined card ends the payment as failed with a reason")
def test_declined_card_ends_the_payment_as_failed() -> None:
    """Steps: tests/bdd/steps/provider.py"""
