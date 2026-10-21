"""Soft computed-style checks: collect every mismatch, fail once at the end.

`StyleCollector.check(locator, expected)` reads the browser's final value of each CSS property and
records one `StyleMismatch` per difference instead of raising, so a test that compares several
elements reports all of them in a single run. For each mismatch the element is outlined, a
screenshot is attached to the Allure step, and the element's inline style is put back, so later
checks see the page as it was. The outline is not a property the design tokens check.

The test ends with `verify()`, which raises one AssertionError listing every mismatch. A test
that forgets it cannot pass silently: the `soft_styles` fixture (tests/ui/conftest.py) calls
`assert_none_pending()` at teardown, which fails while recorded mismatches were never raised.
"""

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field, replace

import allure
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator

from tests.utils import aaa
from tests.utils.ui_steps import describe_locator

_READ_STYLES = (
    "(e, names) => Object.fromEntries(names.map(n => [n, getComputedStyle(e).getPropertyValue(n)]))"
)
# Inset, so the outline stays inside the element's own box and an element screenshot shows it.
_HIGHLIGHT = (
    "e => { const saved = e.getAttribute('style');"
    " e.style.setProperty('outline', '3px solid #f0f', 'important');"
    " e.style.setProperty('outline-offset', '-3px', 'important'); return saved; }"
)
_RESTORE = (
    "(e, saved) => saved === null ? e.removeAttribute('style') : e.setAttribute('style', saved)"
)


@dataclass(frozen=True)
class StyleMismatch:
    element: str  # the locator as the page object wrote it
    prop: str
    expected: str
    actual: str
    screenshot: bytes | None = field(default=None, repr=False)

    def line(self) -> str:
        return f'{self.element}: {self.prop} expected "{self.expected}", actual "{self.actual}"'


def find_mismatches(
    element: str, expected: dict[str, str], actual: dict[str, str]
) -> list[StyleMismatch]:
    """One record per expected property whose actual value differs (or is missing)."""
    return [
        StyleMismatch(element, prop, value, actual.get(prop, ""))
        for prop, value in expected.items()
        if actual.get(prop) != value
    ]


def format_summary(mismatches: list[StyleMismatch]) -> str:
    elements = len({m.element for m in mismatches})
    noun = "mismatch" if len(mismatches) == 1 else "mismatches"
    head = f"{len(mismatches)} style {noun} on {elements} element(s):"
    return "\n".join([head, *(f"  {m.line()}" for m in mismatches)])


class StyleCollector:
    """Per-test: one instance per test, created by the `soft_styles` fixture."""

    def __init__(self, wait_visible: Callable[[Locator], None]) -> None:
        self._wait_visible = wait_visible
        self._pending: list[StyleMismatch] = []

    @property
    def pending(self) -> list[StyleMismatch]:
        """Mismatches recorded and not yet raised by `verify()`."""
        return list(self._pending)

    def check(self, locator: Locator, expected: dict[str, str]) -> None:
        """Compare the element's computed style with `expected`; record, never raise on a
        difference. An element that is not visible still fails at once (nothing to compare)."""
        self._wait_visible(locator)
        element = describe_locator(locator)
        actual: dict[str, str] = locator.evaluate(_READ_STYLES, list(expected))
        found = find_mismatches(element, expected, actual)
        title = f"{element} has the expected style ({len(expected)} properties)"
        # The step is failed by the AssertionError and the report shows it, while the test goes on.
        with suppress(AssertionError), aaa.check(title):
            if found:
                # One screenshot per element, shared by its mismatches.
                png = self._highlighted_screenshot(locator)
                found = [replace(m, screenshot=png) for m in found]
                self._pending.extend(found)
                if png:
                    props = ", ".join(m.prop for m in found)
                    allure.attach(png, f"{element}: {props}", allure.attachment_type.PNG)
                raise AssertionError(format_summary(found))

    def verify(self) -> None:
        """Raise one AssertionError with every recorded mismatch; the last line of the test."""
        if self._pending:
            summary = format_summary(self._pending)
            self._pending.clear()
            raise AssertionError(summary)

    def assert_none_pending(self) -> None:
        """Fixture teardown: a test that recorded mismatches and never called `verify()` fails."""
        if self._pending:
            summary = format_summary(self._pending)
            self._pending.clear()
            raise AssertionError(f"verify() was not called; {summary}")

    @staticmethod
    def _highlighted_screenshot(locator: Locator) -> bytes | None:
        """The element outlined in a screenshot; its inline style is restored in every case."""
        saved = locator.evaluate(_HIGHLIGHT)
        try:
            return locator.screenshot()
        except PlaywrightError:  # e.g. a zero-size element cannot be captured
            return None
        finally:
            locator.evaluate(_RESTORE, saved)
