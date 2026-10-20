"""Seeded bugs: deliberate defects used to prove the test suite can fail (see seeded-bugs.yml).

SEEDED_BUGS is "all" or a comma list such as "BUG-1,BUG-3"; unset or empty means a correct app.
Each defect site has one small, commented `if bug_enabled("BUG-n")`.

  BUG-1  idempotency replay creates a second payment      (routers/payments.py: create_payment)
  BUG-2  refund over the amount is accepted               (routers/payments.py: refund_payment)
  BUG-3  GET /payments/{id} returns another merchant's    (routers/payments.py: get_payment)
  BUG-4  provider timeout leaves the payment `authorized` (routers/payments.py: authorize_payment)
"""

import logging

from app.config import get_settings

BUG_IDS = frozenset({"BUG-1", "BUG-2", "BUG-3", "BUG-4"})

logger = logging.getLogger("uvicorn.error")


def _enabled_ids() -> frozenset[str]:
    raw = get_settings().seeded_bugs.strip()
    if raw.lower() == "all":
        return BUG_IDS
    return frozenset(part.strip().upper() for part in raw.split(",") if part.strip())


def bug_enabled(bug_id: str) -> bool:
    return bug_id in _enabled_ids()


def announce_seeded_bugs() -> None:
    """Called at startup: refuse a typo (it would silently run a correct app), shout otherwise."""
    enabled = _enabled_ids()
    if unknown := enabled - BUG_IDS:
        raise RuntimeError(f"SEEDED_BUGS names unknown bug(s): {sorted(unknown)}")
    if enabled:
        logger.warning(
            "SEEDED BUGS ENABLED: %s. This app is deliberately defective; never use it for real.",
            ", ".join(sorted(enabled)),
        )
