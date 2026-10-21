"""Arrange / Act / Assert as Allure steps.

Most of it is automatic, so a test needs no extra code to read as three phases in the report:

- Arrange: `MerchantFactory.create` and `PaymentFactory.create` are steps named `Arrange: ...`,
  and the requests they make sit inside them.
- Act: a request the test makes itself, and a page-object action, is `Act: ...` (only while the
  test body runs, so fixture setup and teardown stay unlabelled).
- Assert: `expect(...)`, `expect_error(...)` and browser `expect(...)` checks are `Assert: ...`.

A plain `assert` statement is not a step. Where a test should show its structure anyway, it wraps
the code in `arrange(...)`, `act(...)` and `check(...)` below. Phases never nest: inside one, the
automatic labels are off, so nothing is labelled twice.

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

_test_body_running = False  # set by the runtest hook
_depth = 0  # explicit phases (and automatic Arrange steps) currently open


def set_test_body_running(running: bool) -> None:
    global _test_body_running
    _test_body_running = running


def labelling() -> bool:
    """True while the test body runs and no phase is open."""
    return _test_body_running and _depth == 0


@contextmanager
def _phase(prefix: str, title: str) -> Iterator[None]:
    global _depth
    if _depth:  # already inside a phase: the outer step is the one that counts
        yield
        return
    _depth += 1
    try:
        with allure.step(f"{prefix}: {title}"):
            yield
    finally:
        _depth -= 1


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
