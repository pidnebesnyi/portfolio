from uuid import UUID

from pydantic import TypeAdapter

from tests.clients.http import LoggedHttpClient
from tests.models.provider import ChargeRecord

_CHARGES = TypeAdapter(list[ChargeRecord])


class ProviderMockApi:
    """Read side of the provider mock: what it was asked to charge. Test-only endpoint."""

    def __init__(self, http: LoggedHttpClient) -> None:
        self._http = http

    def charges_for(self, payment_id: UUID) -> list[ChargeRecord]:
        """Charges that carry this payment's id as reference. Card tokens repeat across tests
        (and xdist workers), the payment id does not, so this is exactly one test's traffic."""
        raw = self._http.request("GET", "/__requests", params={"reference": str(payment_id)})
        assert raw.status_code == 200, raw.text
        return _CHARGES.validate_json(raw.content)
