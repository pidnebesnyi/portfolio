from datetime import datetime
from uuid import UUID

from tests.models.base import ApiModel
from tests.models.payments import PaymentStatus


class PaymentEvent(ApiModel):
    """Body of a message on the payments.events exchange (routing key = `type`)."""

    event_id: UUID
    type: str
    payment_id: UUID
    merchant_id: UUID
    amount: int
    refund_amount: int | None
    refunded_amount: int
    status: PaymentStatus
    occurred_at: datetime
    request_id: str | None
