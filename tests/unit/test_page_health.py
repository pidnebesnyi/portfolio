"""Which HTTP errors a browser test may see, and how the rest are reported
(tests/utils/page_health.py).

Pure unit tests: no app, no database, no browser. The listener is fed stand-in responses.
"""

from types import SimpleNamespace

import allure
import pytest

from tests.utils.allure_links import area
from tests.utils.page_health import (
    Allowance,
    PageHealthMonitor,
    SeenResponse,
    allowance_from_marker,
    format_report,
    unexpected_errors,
)

pytestmark = [pytest.mark.regression, area("Reporting")]

BASE = "http://app:8000"
STATUS_URL = f"{BASE}/ui/payments/6f1c/status"


def seen(url: str, status: int, method: str = "GET", kind: str = "fetch") -> SeenResponse:
    return SeenResponse(method=method, url=url, status=status, resource_type=kind)


def reply(url: str, status: int, method: str = "GET", kind: str = "fetch") -> SimpleNamespace:
    """What the monitor reads from a Playwright Response."""
    return SimpleNamespace(
        url=url, status=status, request=SimpleNamespace(method=method, resource_type=kind)
    )


@allure.title("Without any allowance every error response is unexpected, successes never are")
def test_without_allowances_every_error_is_unexpected() -> None:
    responses = [seen(BASE + "/a", 200), seen(BASE + "/b", 399), seen(BASE + "/c", 400)]
    responses += [seen(BASE + "/d", 404), seen(BASE + "/e", 500)]

    found = unexpected_errors(responses, [])

    assert [r.url for r in found] == [BASE + "/c", BASE + "/d", BASE + "/e"]


@pytest.mark.parametrize(
    ("allowance", "url", "status", "allowed"),
    [
        (Allowance("r", url="*/status"), STATUS_URL, 500, True),
        (Allowance("r", url="*/status"), BASE + "/ui/payments", 500, False),
        (Allowance("r", statuses=frozenset({500})), STATUS_URL, 500, True),
        (Allowance("r", statuses=frozenset({500})), STATUS_URL, 503, False),
        (Allowance("r", url="*/status", statuses=frozenset({500, 503})), STATUS_URL, 503, True),
        (Allowance("r", url="*/status", statuses=frozenset({500})), BASE + "/x", 500, False),
        (Allowance("r", url="*/status", statuses=frozenset({500})), STATUS_URL, 404, False),
        (Allowance("r", url="**/ui/payments/*/status"), STATUS_URL, 401, True),
    ],
)
@allure.title("An allowance covers a response only when every field it sets matches")
def test_an_allowance_needs_every_field_to_match(
    allowance: Allowance, url: str, status: int, allowed: bool
) -> None:
    assert (unexpected_errors([seen(url, status)], [allowance]) == []) is allowed


@allure.title("One allowance does not hide other errors in the same test")
def test_one_allowance_does_not_hide_other_errors() -> None:
    allowance = Allowance("stubbed", url="*/status", statuses=frozenset({500}))
    responses = [seen(STATUS_URL, 500), seen(BASE + "/logo.png", 404, kind="image")]

    found = unexpected_errors(responses, [allowance])

    assert found == [responses[1]]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {"url": "*/status", "status": 500, "reason": " stub "},
            Allowance("stub", "*/status", frozenset({500})),
        ),
        ({"status": [500, 503], "reason": "x"}, Allowance("x", None, frozenset({500, 503}))),
        ({"url": "*/status", "reason": "x"}, Allowance("x", "*/status", frozenset())),
    ],
)
@allure.title("The marker arguments become an allowance")
def test_marker_arguments_become_an_allowance(kwargs: dict, expected: Allowance) -> None:
    assert allowance_from_marker(**kwargs) == expected


@pytest.mark.parametrize(
    ("args", "kwargs", "problem"),
    [
        ((), {"url": "*/x"}, "reason"),
        ((), {"url": "*/x", "reason": "  "}, "reason"),
        ((), {"reason": "x"}, "must not allow every error"),
        ((), {"status": 200, "reason": "x"}, "400-599"),
        ((), {"status": "500", "reason": "x"}, "400-599"),
        ((), {"url": "", "reason": "x"}, "url"),
        ((), {"urls": "*/x", "reason": "x"}, "unknown"),
        (("*/x",), {"reason": "x"}, "keyword"),
    ],
)
@allure.title("A marker that would hide errors silently or has no reason is refused")
def test_a_misused_marker_is_refused(args: tuple, kwargs: dict, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        allowance_from_marker(*args, **kwargs)


@allure.title("The report lists method, URL, status and resource type of each error")
def test_the_report_lists_each_error() -> None:
    report = format_report(
        [seen(BASE + "/logo.png", 404, kind="image"), seen(STATUS_URL, 500, "POST")]
    )

    assert f"GET {BASE}/logo.png -> 404 (image)" in report
    assert f"POST {STATUS_URL} -> 500 (fetch)" in report
    assert report.startswith("2 unexpected HTTP error response(s)")
    assert "allow_http_errors" in report  # says how to allow it on purpose


@allure.title("The monitor records only error responses, and calls its hooks for every response")
def test_the_monitor_records_errors_and_feeds_hooks() -> None:
    monitor = PageHealthMonitor()
    heard: list[int] = []
    monitor.hooks.append(lambda response: heard.append(response.status))

    monitor.handle(reply(BASE + "/ui/payments", 200))
    monitor.handle(reply(BASE + "/ui/login", 303))
    monitor.handle(reply(BASE + "/logo.png", 404, kind="image"))

    assert heard == [200, 303, 404]
    assert monitor.errors == [seen(BASE + "/logo.png", 404, kind="image")]


@allure.title("A missing favicon is the only error every page may get")
def test_a_missing_favicon_is_allowed_everywhere_but_other_errors_are_not() -> None:
    monitor = PageHealthMonitor()
    monitor.handle(reply(BASE + "/favicon.ico", 404, kind="other"))
    assert monitor.unexpected() == []

    monitor.handle(reply(BASE + "/favicon.ico", 500, kind="other"))
    monitor.handle(reply(BASE + "/app.js", 404, kind="script"))

    assert [(e.url, e.status) for e in monitor.unexpected()] == [
        (BASE + "/favicon.ico", 500),
        (BASE + "/app.js", 404),
    ]


@allure.title("Per-test allowances are added to the global ones")
def test_per_test_allowances_are_added_to_the_global_ones() -> None:
    monitor = PageHealthMonitor([Allowance("stub", "*/status", frozenset({500}))])

    monitor.handle(reply(STATUS_URL, 500))
    monitor.handle(reply(BASE + "/favicon.ico", 404))

    assert monitor.unexpected() == []
