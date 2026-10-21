"""Polling with a deadline, for effects that land shortly after the response (log lines, events).

A fixed sleep is either too short (flaky) or too long (slow); this returns the moment the
condition holds and fails with the last thing it saw when the deadline passes.

Each wait is one Allure step, `Wait until <what>`, with every attempt in a "Polling attempts"
attachment (one line per attempt, or per run of identical outcomes), on success and on timeout.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import allure

from tests.utils import aaa

POLL_INTERVAL_S = 0.05
ATTEMPTS_ATTACHMENT = "Polling attempts"


@dataclass(frozen=True)
class Attempt:
    number: int  # 1-based
    elapsed_ms: int  # since the wait started
    outcome: str  # "not yet: <reason>", "None" or "ok"


def not_yet(exc: AssertionError) -> str:
    """Outcome of an attempt that said "not yet"; a multi-line reason is joined onto one line."""
    reason = " ".join(str(exc).split()) or "no reason given"
    return f"not yet: {reason}"


def attempts_text(attempts: Sequence[Attempt]) -> str:
    """One line per attempt, except that consecutive identical outcomes share a line:
    `#3-#41 (39x)  150-2010 ms  not yet: no log line with request_id=...`."""
    runs: list[list[Attempt]] = []
    for attempt in attempts:
        if runs and runs[-1][-1].outcome == attempt.outcome:
            runs[-1].append(attempt)
        else:
            runs.append([attempt])
    return "\n".join(_run_line(run) for run in runs)


def _run_line(run: list[Attempt]) -> str:
    first, last = run[0], run[-1]
    if len(run) == 1:
        return f"#{first.number}  {first.elapsed_ms} ms  {first.outcome}"
    return (
        f"#{first.number}-#{last.number} ({len(run)}x)"
        f"  {first.elapsed_ms}-{last.elapsed_ms} ms  {first.outcome}"
    )


def timeout_message(
    describe: str, timeout_s: float, reason: str, attempts: Sequence[Attempt]
) -> str:
    """The failure text: the original message first, then how hard it was tried."""
    elapsed_ms = attempts[-1].elapsed_ms if attempts else 0
    return (
        f"gave up after {timeout_s} s waiting for {describe}: {reason}"
        f" ({len(attempts)} attempts, {elapsed_ms} ms)"
    )


def step_title(describe: str) -> str:
    """`Wait until ...`, labelled `Assert:` in the test body like the other checks."""
    title = f"Wait until {describe}"
    return f"Assert: {title}" if aaa.labelling() else title


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def eventually[T](probe: Callable[[], T | None], *, describe: str, timeout_s: float = 10.0) -> T:
    """Call `probe` until it returns something other than None, or fail after `timeout_s`.

    `probe` may raise AssertionError to say "not yet" with a reason; the last reason is reported.
    """
    started = time.monotonic()
    attempts: list[Attempt] = []
    with allure.step(step_title(describe)):
        try:
            return _poll(
                probe,
                describe=describe,
                timeout_s=timeout_s,
                started=started,
                attempts=attempts,
            )
        finally:
            allure.attach(
                attempts_text(attempts),
                name=ATTEMPTS_ATTACHMENT,
                attachment_type=allure.attachment_type.TEXT,
            )


def _poll[T](
    probe: Callable[[], T | None],
    *,
    describe: str,
    timeout_s: float,
    started: float,
    attempts: list[Attempt],
) -> T:
    deadline = started + timeout_s
    reason = "no result yet"
    while True:
        result: T | None = None
        try:
            result = probe()
        except AssertionError as exc:
            reason = str(exc) or reason
            outcome = not_yet(exc)
        else:
            outcome = "None" if result is None else "ok"
        attempts.append(Attempt(len(attempts) + 1, _elapsed_ms(started), outcome))
        if result is not None:
            return result
        if time.monotonic() >= deadline:
            raise AssertionError(timeout_message(describe, timeout_s, reason, attempts))
        time.sleep(POLL_INTERVAL_S)  # the only sleep: bounded by the deadline above
