"""The most recent HTTP exchange and SQL query of the running test, kept so the failure hook in
conftest can attach them to the Allure result. Everything stored here is already masked.

One test runs at a time per pytest process (xdist workers are separate processes), so a plain
module-level state is enough.
"""

from dataclasses import dataclass, field


@dataclass
class _Evidence:
    request: str | None = None
    response: str | None = None
    sql: str | None = None
    sql_result: str | None = None
    # Other evidence by attachment name, e.g. the app's log lines or the events a consumer saw.
    extras: dict[str, str] = field(default_factory=dict)


_state = _Evidence()


def reset() -> None:
    global _state
    _state = _Evidence()


def record_http(request: str, response: str) -> None:
    _state.request, _state.response = request, response


def record_sql(sql: str, result: str) -> None:
    _state.sql, _state.sql_result = sql, result


def record_extra(name: str, text: str) -> None:
    """Keep the latest text under this attachment name (a later call replaces the earlier one)."""
    _state.extras[name] = text


def snapshot() -> _Evidence:
    return _state
