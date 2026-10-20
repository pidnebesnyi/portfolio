from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from tests.clients.http import LoggedHttpClient
from tests.clients.responses import ApiResponse, drop_none, parse
from tests.models.payments import Payment, PaymentList, PaymentStatus, Refund


class _Auto(Enum):
    KEY = "auto"


AUTO_KEY = _Auto.KEY
"""Default for `idempotency_key`: generate a fresh UUID. Pass None to omit the header."""


class PaymentsApi:
    """Typed client for the merchant-facing payment endpoints, bound to one token."""

    def __init__(self, http: LoggedHttpClient, token: str | None) -> None:
        self._http = http
        self.token = token

    def with_token(self, token: str | None) -> PaymentsApi:
        """Same API, different caller identity (None = anonymous)."""
        return PaymentsApi(self._http, token)

    def create(
        self,
        *,
        amount: int = 1050,
        currency: str = "UAH",
        description: str = "test payment",
        card_token: str = "tok_success",
        idempotency_key: str | _Auto | None = AUTO_KEY,
    ) -> ApiResponse[Payment]:
        body = {
            "amount": amount,
            "currency": currency,
            "description": description,
            "card_token": card_token,
        }
        return self.create_raw(body, idempotency_key=idempotency_key)

    def create_raw(
        self, body: dict[str, Any], *, idempotency_key: str | _Auto | None = AUTO_KEY
    ) -> ApiResponse[Payment]:
        """Send an arbitrary body (for validation tests)."""
        key = str(uuid4()) if isinstance(idempotency_key, _Auto) else idempotency_key
        headers = {"Idempotency-Key": key} if key is not None else {}
        raw = self._http.request(
            "POST", "/payments", token=self.token, json_body=body, headers=headers
        )
        return parse(raw, Payment)

    def get(self, payment_id: UUID) -> ApiResponse[Payment]:
        return parse(
            self._http.request("GET", f"/payments/{payment_id}", token=self.token), Payment
        )

    def list_payments(
        self,
        *,
        status: PaymentStatus | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> ApiResponse[PaymentList]:
        params = drop_none(
            {
                "status": status.value if status else None,
                "created_from": created_from.isoformat() if created_from else None,
                "created_to": created_to.isoformat() if created_to else None,
                "limit": limit,
                "offset": offset,
            }
        )
        return parse(
            self._http.request("GET", "/payments", token=self.token, params=params), PaymentList
        )

    def list_raw(self, params: dict[str, Any]) -> ApiResponse[PaymentList]:
        """Send arbitrary query parameters (for validation tests)."""
        raw = self._http.request("GET", "/payments", token=self.token, params=params)
        return parse(raw, PaymentList)

    def authorize(self, payment_id: UUID) -> ApiResponse[Payment]:
        return self._action(payment_id, "authorize")

    def capture(self, payment_id: UUID) -> ApiResponse[Payment]:
        return self._action(payment_id, "capture")

    def void(self, payment_id: UUID) -> ApiResponse[Payment]:
        return self._action(payment_id, "void")

    def refund(self, payment_id: UUID, amount: int) -> ApiResponse[Refund]:
        raw = self._http.request(
            "POST",
            f"/payments/{payment_id}/refunds",
            token=self.token,
            json_body={"amount": amount},
        )
        return parse(raw, Refund)

    def _action(self, payment_id: UUID, action: str) -> ApiResponse[Payment]:
        raw = self._http.request("POST", f"/payments/{payment_id}/{action}", token=self.token)
        return parse(raw, Payment)
