from pydantic import BaseModel, ConfigDict


class LogLine(BaseModel):
    """One JSON line of the app's log. Extra fields vary by event, so they are allowed; the
    ones every line has, and the ones the access line has, are typed."""

    model_config = ConfigDict(extra="allow")

    ts: str
    event: str
    request_id: str
    # http.request
    method: str | None = None
    path: str | None = None
    status: int | None = None
    duration_ms: float | None = None
    merchant_id: str | None = None
    # domain events (payment.*, refund.*)
    payment_id: str | None = None
    action: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    amount: int | None = None
    refunded_amount: int | None = None
    refundable: int | None = None
    reason: str | None = None
    # event.published / event.publish_failed
    event_id: str | None = None
    type: str | None = None
