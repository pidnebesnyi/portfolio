"""Soft style checks (tests/utils/soft_checks.py) with a fake locator.

Pure unit tests: no app, no database, no browser.
"""

from typing import Any, cast

import allure
import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator

from tests.ui import design_tokens
from tests.utils.allure_links import area
from tests.utils.soft_checks import (
    StyleCollector,
    StyleMismatch,
    find_mismatches,
    format_summary,
)

pytestmark = [pytest.mark.regression, area("Reporting")]


class _Locator:
    """Answers the three evaluate calls and the screenshot the way a page would."""

    def __init__(self, selector: str, styles: dict[str, str], inline: str | None = None) -> None:
        self._selector = selector
        self._styles = styles
        self.inline = inline  # the element's style attribute
        self.during_screenshot: str | None = None
        self.screenshot_error: Exception | None = None

    def __str__(self) -> str:
        return f"<Locator frame=<Frame name= url='http://app/ui'> selector='{self._selector}'>"

    def evaluate(self, script: str, arg: Any = None) -> Any:
        if "getComputedStyle" in script:
            return {name: self._styles.get(name, "") for name in arg}
        if "outline" in script:  # highlight
            saved = self.inline
            self.inline = (saved or "") + "outline: 3px solid #f0f;"
            return saved
        self.inline = arg  # restore
        return None

    def screenshot(self) -> bytes:
        self.during_screenshot = self.inline
        if self.screenshot_error:
            raise self.screenshot_error
        return b"png"


def _collector() -> StyleCollector:
    return StyleCollector(wait_visible=lambda locator: None)


def _check(collector: StyleCollector, locator: _Locator, expected: dict[str, str]) -> None:
    collector.check(cast(Locator, locator), expected)


@allure.title("Only the properties that differ, or are missing, become mismatches")
def test_only_differing_properties_are_mismatches() -> None:
    found = find_mismatches(
        "body",
        {"font-size": "15px", "color": "rgb(0, 0, 0)", "display": "block"},
        {"font-size": "16px", "color": "rgb(0, 0, 0)"},
    )

    assert [(m.prop, m.expected, m.actual) for m in found] == [
        ("font-size", "15px", "16px"),
        ("display", "block", ""),
    ]


@allure.title("The summary counts mismatches and elements and lists each one")
def test_summary_lists_every_mismatch() -> None:
    summary = format_summary(
        [
            StyleMismatch("body", "font-size", "15px", "16px"),
            StyleMismatch("body", "color", "red", "blue"),
            StyleMismatch("h1", "display", "block", "inline"),
        ]
    )

    assert summary.splitlines() == [
        "3 style mismatches on 2 element(s):",
        '  body: font-size expected "15px", actual "16px"',
        '  body: color expected "red", actual "blue"',
        '  h1: display expected "block", actual "inline"',
    ]


@allure.title("Matching styles record nothing and verify passes")
def test_matching_styles_pass() -> None:
    collector = _collector()

    _check(collector, _Locator("body", {"font-size": "15px"}), {"font-size": "15px"})

    collector.verify()
    assert collector.pending == []


@allure.title("Mismatches on several elements are all raised by one verify")
def test_verify_raises_every_recorded_mismatch_once() -> None:
    collector = _collector()
    _check(collector, _Locator("body", {"font-size": "16px"}), {"font-size": "15px"})
    _check(
        collector,
        _Locator('internal:testid=[data-testid="flash"s]', {"display": "inline"}),
        {"display": "block"},
    )

    with pytest.raises(AssertionError) as raised:
        collector.verify()

    assert str(raised.value).splitlines() == [
        "2 style mismatches on 2 element(s):",
        '  body: font-size expected "15px", actual "16px"',
        '  get_by_test_id("flash"): display expected "block", actual "inline"',
    ]
    collector.verify()  # raised once: nothing is left to raise


@allure.title("check itself does not raise on a mismatch, so the test goes on")
def test_check_records_instead_of_raising() -> None:
    collector = _collector()

    _check(collector, _Locator("body", {"color": "red"}), {"color": "blue"})

    assert [m.prop for m in collector.pending] == ["color"]


@allure.title("A test that never called verify fails at teardown while mismatches are pending")
def test_teardown_fails_when_verify_was_not_called() -> None:
    collector = _collector()
    _check(collector, _Locator("body", {"color": "red"}), {"color": "blue"})

    with pytest.raises(AssertionError, match=r"(?s)verify\(\) was not called.*color"):
        collector.assert_none_pending()


@allure.title("Teardown is quiet when nothing was recorded or verify already raised")
def test_teardown_passes_when_nothing_is_pending() -> None:
    collector = _collector()
    collector.assert_none_pending()
    _check(collector, _Locator("body", {"color": "red"}), {"color": "blue"})
    with pytest.raises(AssertionError):
        collector.verify()

    collector.assert_none_pending()


@allure.title("Collectors do not share state")
def test_collectors_are_independent() -> None:
    first, second = _collector(), _collector()

    _check(first, _Locator("body", {"color": "red"}), {"color": "blue"})

    assert second.pending == []
    second.verify()


@pytest.mark.parametrize("inline", [None, "color: red;"], ids=["no-style", "own-style"])
@allure.title("The element is outlined for the screenshot and its style attribute restored")
def test_highlight_is_removed_after_the_screenshot(inline: str | None) -> None:
    locator = _Locator("body", {"color": "red"}, inline)
    collector = _collector()

    _check(collector, locator, {"color": "blue"})

    assert "outline" in (locator.during_screenshot or "")
    assert locator.inline == inline
    assert collector.pending[0].screenshot == b"png"


@allure.title("A screenshot that fails still restores the element and keeps the mismatch")
def test_failed_screenshot_still_restores_the_element() -> None:
    locator = _Locator("body", {"color": "red"}, "color: red;")
    locator.screenshot_error = PlaywrightError("element is not visible")
    collector = _collector()

    _check(collector, locator, {"color": "blue"})

    assert locator.inline == "color: red;"
    assert collector.pending[0].screenshot is None


@allure.title("The highlight is not a property the design tokens check")
def test_design_tokens_do_not_check_the_outline() -> None:
    checked = {
        prop for value in vars(design_tokens).values() if isinstance(value, dict) for prop in value
    }

    assert checked
    assert not {prop for prop in checked if prop.startswith("outline")}
