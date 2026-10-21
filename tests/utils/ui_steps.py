"""Browser assertions as Allure steps.

Playwright's `expect(locator).to_have_text(...)` is plain code to Allure, so a UI test showed only
the API calls that built its data. `install()` wraps every `to_*` / `not_to_*` method of
Playwright's assertion classes so each check becomes a step named after the locator and the
expectation, e.g. `Assert: get_by_test_id("payment-status") to have text "refunded"`. The wrapper
adds nothing else: the assertion, its auto-waiting and its error message are Playwright's own.

Page-object actions are steps too (`@allure.step` on the methods), with titles written to leave
typed secrets out; the values checked by assertions are page text, never credentials.
"""

import functools
import re
import threading
from collections.abc import Callable
from typing import Any

import allure
from playwright.sync_api import LocatorAssertions, PageAssertions

_SELECTOR = re.compile(r"selector='(?P<selector>.*)'>$")
_TESTID = re.compile(r'^internal:testid=\[data-testid="(?P<v>.*)"s\]$')
_LABEL = re.compile(r'^internal:label="(?P<v>.*)"[is]$')
_ROLE = re.compile(r"^internal:role=(?P<v>.*)$")
_TEXT = re.compile(r'^internal:text="(?P<v>.*)"[is]$')
_MAX = 80
_STATE = threading.local()


def describe_locator(locator: object) -> str:
    """`get_by_test_id("payment-status")` for a Playwright locator, its raw selector otherwise."""
    match = _SELECTOR.search(str(locator))
    if not match:
        return "element"
    parts = []
    for part in match["selector"].split(" >> "):
        for pattern, template in (
            (_TESTID, 'get_by_test_id("{}")'),
            (_LABEL, 'get_by_label("{}")'),
            (_TEXT, 'get_by_text("{}")'),
            (_ROLE, "get_by_role({})"),
        ):
            if found := pattern.match(part):
                parts.append(template.format(found["v"]))
                break
        else:
            parts.append(part)
    return " >> ".join(parts)


def _short(value: Any) -> str:
    text = value.pattern if isinstance(value, re.Pattern) else str(value)
    shown = text if len(text) <= _MAX else text[: _MAX - 1] + "…"
    return f'"{shown}"' if isinstance(value, str | re.Pattern) else shown


def step_title(subject: str, method: str, args: tuple[Any, ...]) -> str:
    """`Assert: <subject> to have text "x"` from the method name and its first argument."""
    words = method.replace("not_to_", "not to ").replace("to_", "to ").replace("_", " ")
    expected = f" {_short(args[0])}" if args else ""
    return f"Assert: {subject} {words}{expected}"


def _subject(assertions: object, method: str) -> str:
    # The public class wraps an implementation object that holds the locator or the page.
    impl = getattr(assertions, "_impl_obj", None)
    if method.endswith(("_url", "_title")):  # page assertions are built on the page's :root
        return "the page"
    if (locator := getattr(impl, "_actual_locator", None)) is not None:
        return describe_locator(locator)
    return "value"


def _wrap(cls: type, name: str) -> None:
    original: Callable[..., Any] = getattr(cls, name)
    if getattr(original, "_allure_step", False):
        return

    @functools.wraps(original)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        # not_to_x delegates to to_x on a negated twin: one step per check, not two.
        if getattr(_STATE, "inside", False):
            return original(self, *args, **kwargs)
        _STATE.inside = True
        try:
            with allure.step(step_title(_subject(self, name), name, args)):
                return original(self, *args, **kwargs)
        finally:
            _STATE.inside = False

    wrapper._allure_step = True  # type: ignore[attr-defined]
    setattr(cls, name, wrapper)


def install() -> None:
    """Idempotent; safe to call from every session fixture that needs it."""
    for cls in (LocatorAssertions, PageAssertions):
        for name in dir(cls):
            if name.startswith(("to_", "not_to_")):
                _wrap(cls, name)
