"""Page health: a browser test fails when the page it drives got an HTTP error it did not expect.

A broken image, script or `fetch` call behind a page that otherwise looks fine is invisible to
`expect(...)`. The `page_health` fixture (tests/conftest.py) listens to every response of the
page and, at teardown, fails the test if a response with status >= 400 was not allowed.

Allowed errors are declared per test, with a reason, so the exception is visible in the code:

    @pytest.mark.allow_http_errors(url="*/ui/payments/*/status", status=500, reason="stubbed")

Everything that decides what is expected, and how it is reported, is plain Python in this module
(unit-tested in tests/unit/test_page_health.py). `PageHealthMonitor` is the only part that
touches the browser; other response checks can join the same listener through `hooks`.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

ALLOW_HTTP_ERRORS = "allow_http_errors"
ERROR_FROM = 400


@dataclass(frozen=True)
class SeenResponse:
    method: str
    url: str
    status: int
    resource_type: str  # Playwright's name: document, fetch, image, script, ...


@dataclass(frozen=True)
class Allowance:
    """Responses that may be errors. Every field that is set must match; `reason` is for people."""

    reason: str
    url: str | None = None  # glob over the full URL, e.g. "*/ui/payments/*/status"
    statuses: frozenset[int] = frozenset()  # empty: any error status

    def matches(self, seen: SeenResponse) -> bool:
        if self.url is not None and not fnmatchcase(seen.url, self.url):
            return False
        return not self.statuses or seen.status in self.statuses


# Noise every page may produce. Pages declare no icon, so a browser that asks for the default
# location gets the service's JSON 404; that says nothing about the page.
GLOBAL_ALLOWANCES = (
    Allowance(
        reason="the pages declare no icon; browsers may still ask for the default one",
        url="*/favicon.ico",
        statuses=frozenset({404}),
    ),
)


def allowance_from_marker(*args: Any, **kwargs: Any) -> Allowance:
    """Build an Allowance from the arguments of `@pytest.mark.allow_http_errors(...)`.

    Raises ValueError with a message fit for a collection error when the marker is misused: it
    needs a reason, and a url and/or a status (otherwise it would silence every error)."""
    if args:
        raise ValueError(
            f"{ALLOW_HTTP_ERRORS} takes keyword arguments only: url=, status=, reason="
        )
    unknown = sorted(kwargs.keys() - {"url", "status", "reason"})
    if unknown:
        raise ValueError(f"{ALLOW_HTTP_ERRORS}: unknown argument(s) {unknown}")
    reason = kwargs.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"{ALLOW_HTTP_ERRORS} needs reason=... saying why the error is expected")
    url = kwargs.get("url")
    if url is not None and not (isinstance(url, str) and url):
        raise ValueError(f"{ALLOW_HTTP_ERRORS}: url must be a non-empty glob string")
    raw_status = kwargs.get("status")
    if raw_status is None:
        statuses: tuple[Any, ...] = ()
    elif isinstance(raw_status, int):
        statuses = (raw_status,)
    else:
        statuses = tuple(raw_status)
    if bad := [s for s in statuses if not isinstance(s, int) or not ERROR_FROM <= s <= 599]:
        raise ValueError(f"{ALLOW_HTTP_ERRORS}: status must be 400-599, got {bad}")
    if url is None and not statuses:
        raise ValueError(
            f"{ALLOW_HTTP_ERRORS} needs url= and/or status=: it must not allow every error"
        )
    return Allowance(reason=reason.strip(), url=url, statuses=frozenset(statuses))


def unexpected_errors(
    seen: Iterable[SeenResponse], allowances: Iterable[Allowance]
) -> list[SeenResponse]:
    """The error responses (status >= 400) that no allowance covers, in the order they arrived."""
    allowed = tuple(allowances)
    return [
        response
        for response in seen
        if response.status >= ERROR_FROM and not any(a.matches(response) for a in allowed)
    ]


def format_report(errors: Iterable[SeenResponse]) -> str:
    """The Allure attachment: one line per response, then how to allow it on purpose."""
    lines = [f"{e.method} {e.url} -> {e.status} ({e.resource_type})" for e in errors]
    if not lines:
        return "No unexpected HTTP errors."
    return "\n".join(
        [
            f"{len(lines)} unexpected HTTP error response(s) seen by the page:",
            *lines,
            "",
            f"If a test causes these on purpose, mark it with "
            f"@pytest.mark.{ALLOW_HTTP_ERRORS}(url=..., status=..., reason=...).",
        ]
    )


class PageHealthMonitor:
    """Records the error responses of one page. `page.on("response")` also fires for responses
    a test fulfils itself with `route.fulfill`, so stubbed errors need an allowance too.

    `hooks` are called with every Playwright response (any status), so another check can use the
    same listener; a hook should record what it sees and leave judging to teardown."""

    def __init__(self, allowances: Iterable[Allowance] = ()) -> None:
        self.allowances = (*GLOBAL_ALLOWANCES, *allowances)
        self.errors: list[SeenResponse] = []  # every response with status >= 400, in arrival order
        self.hooks: list[Callable[[Any], None]] = []

    def attach(self, page: Any) -> None:
        page.on("response", self.handle)

    def handle(self, response: Any) -> None:
        if response.status >= ERROR_FROM:
            self.errors.append(
                SeenResponse(
                    method=response.request.method,
                    url=response.url,
                    status=response.status,
                    resource_type=response.request.resource_type,
                )
            )
        for hook in self.hooks:
            hook(response)

    def unexpected(self) -> list[SeenResponse]:
        return unexpected_errors(self.errors, self.allowances)
