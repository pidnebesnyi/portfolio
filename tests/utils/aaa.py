"""Arrange / Act / Assert as Allure steps.

Most of it is automatic, so a test needs no extra code to read as three phases in the report:

- Arrange: `MerchantFactory.create` and `PaymentFactory.create` are steps named `Arrange: ...`
  wherever they run, a fixture included, and the requests they make sit inside them.
- Act: a request the test makes itself, and a page-object action, is `Act: ...` (only while the
  test body runs, so requests made by fixtures stay unlabelled).
- Assert: `expect(...)`, `expect_error(...)` and browser `expect(...)` checks are `Assert: ...`.

A plain `assert` statement is not a step. Where a test should show its structure anyway, it wraps
the code in `arrange(...)`, `act(...)` and `check(...)` below. Phases never nest: inside one, the
automatic labels are off, so nothing is labelled twice.

Gherkin scenarios (tests/bdd) already say Given / When / Then, so `start_test(labels_on=False)`
turns every prefix off for them: the same steps appear under their plain names.

The phase state is process-wide, not per thread, so requests sent from the worker threads of
`run_together` fall under the phase that started them. pytest-xdist workers are processes, and a
test runs on one at a time.
"""

import functools
import inspect
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import allure

_labels_on = True  # off for Gherkin scenarios; set per test by the runtest hooks
_test_body_running = False  # set by the runtest hooks
_depth = 0  # explicit phases (and automatic Arrange steps) currently open


def start_test(labels_on: bool) -> None:
    """Before a test's setup: labels on or off, and nothing left open by the previous test."""
    global _labels_on, _test_body_running, _depth
    _labels_on, _test_body_running, _depth = labels_on, False, 0


def set_test_body_running(running: bool) -> None:
    global _test_body_running
    _test_body_running = running


def labelling() -> bool:
    """True while the test body runs, labels are on and no phase is open."""
    return _labels_on and _test_body_running and _depth == 0


def assert_title(text: str) -> str:
    """The step name of a browser check: `Assert: ...`, or `Expect ...` with labels off."""
    return f"Assert: {text}" if _labels_on else f"Expect {text}"


@contextmanager
def _phase(prefix: str, title: str) -> Iterator[None]:
    global _depth
    if _depth:  # already inside a phase: the outer step is the one that counts
        yield
        return
    _depth += 1
    try:
        with allure.step(f"{prefix}: {title}" if _labels_on else title):
            yield
    finally:
        _depth = max(_depth - 1, 0)  # never below zero, even if start_test reset it meanwhile


def arrange(title: str) -> AbstractContextManager[None]:
    return _phase("Arrange", title)


def act(title: str) -> AbstractContextManager[None]:
    return _phase("Act", title)


def check(title: str) -> AbstractContextManager[None]:
    return _phase("Assert", title)


def request_title(method: str, path: str) -> str:
    return f"Act: {method} {path}" if labelling() else f"{method} {path}"


def api_assert(title: str) -> AbstractContextManager[None]:
    """One `Assert:` step around an API response check; no step outside the test body."""
    return _phase("Assert", title) if labelling() else _nothing()


@contextmanager
def _nothing() -> Iterator[None]:
    yield


def page_action[**P, R](title: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """A page-object method as a step. `{name}` in the title is filled from the call's arguments,
    defaults and `self` included, which `@allure.step` cannot do. It is `Act: ...` in the test
    body and a plain step elsewhere (in an explicit phase, or while a fixture logs in)."""

    def decorator(method: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(method)

        @functools.wraps(method)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            values: dict[str, Any] = dict(bound.arguments)
            text = title.format(**values)
            with allure.step(f"Act: {text}" if labelling() else text):
                return method(*args, **kwargs)

        return wrapper

    return decorator


def page_step(title: str) -> AbstractContextManager[None]:
    """`page_action` for a block inside a method, where the title needs computed values."""
    return allure.step(f"Act: {title}" if labelling() else title)
