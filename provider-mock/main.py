"""Placeholder payment provider. Always approves.

Phase 3 replaces this with behaviour chosen by card_token (decline, 500, timeout, slow).
"""

from typing import Any

from fastapi import FastAPI

app = FastAPI(title="Provider mock", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/charge")
def charge(payload: dict[str, Any]) -> dict[str, str]:
    return {"status": "approved"}
