"""Payment provider client behind a small interface, so the HTTP stub can be swapped
(for tests, or for the behaviour-by-token mock in phase 3) without touching the handlers."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import httpx

from app.config import get_settings


class ChargeOutcome(StrEnum):
    APPROVED = "approved"
    DECLINED = "declined"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class ChargeResult:
    outcome: ChargeOutcome
    detail: str | None = None


class ProviderClient(Protocol):
    def charge(self, amount: int, currency: str, card_token: str) -> ChargeResult: ...


class HttpProviderClient:
    def __init__(self, base_url: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        # httpx applies this to connect, read and write separately. Good enough here: a stalled
        # provider is cut off after timeout_s; a slow trickle is not a scenario we model.
        self._timeout = httpx.Timeout(timeout_s)

    def charge(self, amount: int, currency: str, card_token: str) -> ChargeResult:
        try:
            response = httpx.post(
                f"{self._base_url}/charge",
                json={"amount": amount, "currency": currency, "card_token": card_token},
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            return ChargeResult(ChargeOutcome.TIMEOUT)
        except httpx.HTTPError as exc:
            return ChargeResult(ChargeOutcome.ERROR, detail=type(exc).__name__)
        if response.status_code >= 500:
            return ChargeResult(ChargeOutcome.ERROR, detail=f"http {response.status_code}")
        if response.status_code != 200:
            return ChargeResult(
                ChargeOutcome.ERROR, detail=f"unexpected http {response.status_code}"
            )
        try:
            status = response.json().get("status")
        except (ValueError, AttributeError):
            return ChargeResult(ChargeOutcome.ERROR, detail="unparseable provider response")
        if status == "approved":
            return ChargeResult(ChargeOutcome.APPROVED)
        if status == "declined":
            return ChargeResult(ChargeOutcome.DECLINED)
        return ChargeResult(ChargeOutcome.ERROR, detail="unknown provider status")


def get_provider() -> ProviderClient:
    """FastAPI dependency; override in tests via app.dependency_overrides."""
    settings = get_settings()
    return HttpProviderClient(settings.provider_url, settings.provider_timeout_s)
