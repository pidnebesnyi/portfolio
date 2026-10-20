"""Pass/fail rules for a load run, loaded next to the locustfile: `-f locustfile.py,thresholds.py`.

When the test stops, the run is judged against the two numbers below. A breach sets the process
exit code to 1, so `locust --headless` (and the CI job that wraps it) fails. All requests in the run
are counted together; the setup calls in locustfile.py are not part of the statistics.
"""

import logging
from typing import Any

from locust import events
from locust.env import Environment

# One lab-sized app instance on a shared CI runner answers in tens of milliseconds at this load;
# half a second is already visibly slow for a card payment step, so anything above is a regression.
MAX_P95_MS = 500
# One failed request in a hundred is the most a payment flow may lose; any structural error
# (a 4xx/5xx from the flow itself) shows up far above this, a single network blip stays below it.
MAX_ERROR_RATE = 0.01

log = logging.getLogger("thresholds")


def evaluate(p95_ms: float, error_rate: float, requests: int) -> list[str]:
    """Return one message per breached threshold (an empty list means the run passed)."""
    breaches = []
    if requests == 0:
        # No data must not look like a pass (the app was down, or the users never started).
        breaches.append("no requests were made")
    if p95_ms > MAX_P95_MS:
        breaches.append(f"p95 {p95_ms:.0f} ms is above {MAX_P95_MS} ms")
    if error_rate > MAX_ERROR_RATE:
        breaches.append(f"error rate {error_rate:.2%} is above {MAX_ERROR_RATE:.0%}")
    return breaches


def check_thresholds(environment: Environment, **_: Any) -> None:
    total = environment.stats.total
    breaches = evaluate(
        p95_ms=total.get_response_time_percentile(0.95) or 0.0,
        error_rate=total.fail_ratio,
        requests=total.num_requests,
    )
    if breaches:
        for breach in breaches:
            log.error("THRESHOLD BREACHED: %s", breach)
        environment.process_exit_code = 1
    else:
        log.info(
            "Thresholds met: p95 %.0f ms (max %d), error rate %.2f%% (max %.0f%%)",
            total.get_response_time_percentile(0.95) or 0.0,
            MAX_P95_MS,
            total.fail_ratio * 100,
            MAX_ERROR_RATE * 100,
        )
        environment.process_exit_code = 0


events.test_stop.add_listener(check_thresholds)
