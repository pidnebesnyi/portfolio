from uuid import UUID

from pydantic import TypeAdapter

from tests.clients.http import LoggedHttpClient
from tests.models.provider import ChargeRecord, FindRequestsResponse

_FOUND = TypeAdapter(FindRequestsResponse)


class ProviderStub:
    """Verification side of the WireMock provider stub: what the app asked it to charge.

    Uses WireMock's admin API (`POST /__admin/requests/find`). The stub's behaviour itself lives in
    `provider-mock/mappings`; this class only reads the request journal.
    """

    def __init__(self, http: LoggedHttpClient) -> None:
        self._http = http

    def charges_for(self, payment_id: UUID) -> list[ChargeRecord]:
        """Charges that carry this payment's id as `reference`. Card tokens repeat across tests
        (and xdist workers), the payment id does not, so this is exactly one test's traffic.
        The journal is never reset during a run, because that would wipe other tests' traffic."""
        pattern = {
            "method": "POST",
            "urlPath": "/charge",
            "bodyPatterns": [
                {"equalToJson": {"reference": str(payment_id)}, "ignoreExtraElements": True}
            ],
        }
        raw = self._http.request("POST", "/__admin/requests/find", json_body=pattern)
        assert raw.status_code == 200, raw.text
        return [
            ChargeRecord.model_validate_json(logged.body)
            for logged in _FOUND.validate_json(raw.content).requests
        ]
