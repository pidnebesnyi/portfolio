"""Polling with a deadline, for effects that land shortly after the response (log lines, events).

A fixed sleep is either too short (flaky) or too long (slow); this returns the moment the
condition holds and fails with the last thing it saw when the deadline passes.
"""

import time
from collections.abc import Callable

POLL_INTERVAL_S = 0.05


def eventually[T](probe: Callable[[], T | None], *, describe: str, timeout_s: float = 10.0) -> T:
    """Call `probe` until it returns something other than None, or fail after `timeout_s`.

    `probe` may raise AssertionError to say "not yet" with a reason; the last reason is reported.
    """
    deadline = time.monotonic() + timeout_s
    reason = "no result yet"
    while True:
        try:
            result = probe()
        except AssertionError as exc:
            reason = str(exc) or reason
        else:
            if result is not None:
                return result
        if time.monotonic() >= deadline:
            raise AssertionError(f"gave up after {timeout_s} s waiting for {describe}: {reason}")
        time.sleep(POLL_INTERVAL_S)  # the only sleep: bounded by the deadline above
