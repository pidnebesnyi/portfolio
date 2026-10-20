"""Payment provider stub. What a charge does is decided by its card_token, per request, so tests
running in parallel never share state:

  tok_success  approved (also the default for any other token)
  tok_decline  200 with a declined result
  tok_error    HTTP 500
  tok_timeout  answers after 10 s (the app gives up after PROVIDER_TIMEOUT_S, 2 s by default)
  tok_slow     answers after 1 s, still approved

Every charge is recorded on arrival. Tokens repeat across tests, so GET /__requests can also be
filtered by `reference` (the app sends the payment id), which pins down exactly one test's charge.
"""

import asyncio
from collections import deque
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Provider mock", version="0.2.0")

TIMEOUT_SLEEP_S = 10.0  # longer than any sane client timeout, short enough not to pile up
SLOW_SLEEP_S = 1.0  # below the app's 2 s timeout: slow, but must still succeed

# Bounded: a long load run must not grow the container's memory without limit.
_received: deque[dict[str, Any]] = deque(maxlen=10_000)


class ChargeRequest(BaseModel):
    amount: int
    currency: str
    card_token: str
    reference: str | None = None  # idempotency reference; the app sends the payment id


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/charge")
async def charge(payload: ChargeRequest) -> dict[str, str]:
    # Recorded before any sleep, so a charge the app gave up on is still visible to the test.
    _received.append(payload.model_dump())
    match payload.card_token:
        case "tok_decline":
            return {"status": "declined", "reason": "do_not_honor"}
        case "tok_error":
            raise HTTPException(status_code=500, detail="provider exploded")
        case "tok_timeout":
            await asyncio.sleep(TIMEOUT_SLEEP_S)
        case "tok_slow":
            await asyncio.sleep(SLOW_SLEEP_S)
    return {"status": "approved"}


@app.get("/__requests")
def requests_received(
    card_token: str | None = None, reference: str | None = None
) -> list[dict[str, Any]]:
    """Charges received so far, oldest first, optionally filtered by token and/or reference."""
    return [
        r
        for r in _received
        if (card_token is None or r["card_token"] == card_token)
        and (reference is None or r["reference"] == reference)
    ]
