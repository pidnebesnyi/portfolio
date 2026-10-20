from uuid import UUID

from tests.clients.http import LoggedHttpClient
from tests.clients.responses import ApiResponse, parse
from tests.models.base import ApiModel
from tests.models.merchants import Merchant


class _Unused(ApiModel):
    """Placeholder model for 204 responses."""


class MerchantsApi:
    """Admin-only endpoints. Constructed with an admin token."""

    def __init__(self, http: LoggedHttpClient, token: str | None) -> None:
        self._http = http
        self._token = token

    def create(self, name: str, email: str, password: str) -> ApiResponse[Merchant]:
        raw = self._http.request(
            "POST",
            "/merchants",
            token=self._token,
            json_body={"name": name, "email": email, "password": password},
        )
        return parse(raw, Merchant)

    def list_all(self, limit: int = 100) -> list[Merchant]:
        raw = self._http.request("GET", "/merchants", token=self._token, params={"limit": limit})
        assert raw.status_code == 200, raw.text
        return [Merchant.model_validate(item) for item in raw.json()]

    def list_raw(self) -> ApiResponse[_Unused]:
        """Status-only variant for access checks (the body is irrelevant on 401/403)."""
        return parse(self._http.request("GET", "/merchants", token=self._token), None)

    def delete(self, merchant_id: UUID) -> ApiResponse[_Unused]:
        raw = self._http.request("DELETE", f"/merchants/{merchant_id}", token=self._token)
        return parse(raw, None)
