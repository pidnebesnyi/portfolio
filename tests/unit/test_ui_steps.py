"""How browser assertions are named in the Allure report (tests/utils/ui_steps.py).

Pure unit tests: no app, no database, no browser.
"""

import re

import allure
import pytest

from tests.utils.allure_links import area
from tests.utils.ui_steps import describe_locator, step_title

pytestmark = [pytest.mark.regression, area("Reporting")]


class _Locator:
    """Prints the way Playwright's Locator does."""

    def __init__(self, selector: str) -> None:
        self._selector = selector

    def __str__(self) -> str:
        return f"<Locator frame=<Frame name= url='http://app/ui'> selector='{self._selector}'>"


@pytest.mark.parametrize(
    ("selector", "described"),
    [
        ('internal:testid=[data-testid="payment-status"s]', 'get_by_test_id("payment-status")'),
        ('internal:label="Email"i', 'get_by_label("Email")'),
        ("internal:role=heading[level=1]", "get_by_role(heading[level=1])"),
        ('internal:testid=[data-testid="rows"s] >> nth=0', 'get_by_test_id("rows") >> nth=0'),
        ("table tr", "table tr"),
    ],
)
@allure.title("A locator is described the way the page object wrote it: {described}")
def test_locators_are_described_as_the_page_object_wrote_them(
    selector: str, described: str
) -> None:
    assert describe_locator(_Locator(selector)) == described


@pytest.mark.parametrize(
    ("method", "args", "title"),
    [
        ("to_have_text", ("refunded",), 'Assert: x to have text "refunded"'),
        ("not_to_be_visible", (), "Assert: x not to be visible"),
        ("to_have_url", (re.compile(r"/ui/2fa$"),), 'Assert: x to have url "/ui/2fa$"'),
        ("to_have_count", (0,), "Assert: x to have count 0"),
        ("to_have_text", ("a" * 100,), 'Assert: x to have text "' + "a" * 79 + '…"'),
    ],
)
@allure.title("An assertion becomes the step: {title}")
def test_assertions_are_named_by_what_they_check(
    method: str, args: tuple[object, ...], title: str
) -> None:
    assert step_title("x", method, args) == title
