from pydantic import BaseModel

from tests.models.base import ApiModel


class ChargeRecord(ApiModel):
    """The JSON body of one charge request, as the stub received it."""

    amount: int
    currency: str
    card_token: str
    reference: str | None


class LoggedRequest(BaseModel):
    """One entry of WireMock's request journal. WireMock adds many fields (headers, timestamps,
    client address); only the raw request body matters here, the rest is ignored."""

    body: str


class FindRequestsResponse(BaseModel):
    """Answer of `POST /__admin/requests/find`."""

    requests: list[LoggedRequest]
