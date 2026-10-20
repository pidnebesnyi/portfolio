from datetime import datetime
from enum import StrEnum
from uuid import UUID

from tests.models.base import ApiModel


class PaymentStatus(StrEnum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    VOIDED = "voided"
    FAILED = "failed"


class Payment(ApiModel):
    id: UUID
    merchant_id: UUID
    amount: int
    currency: str
    description: str
    card_token: str
    status: PaymentStatus
    failure_reason: str | None = None
    refunded_amount: int
    created_at: datetime
    updated_at: datetime


class PaymentList(ApiModel):
    items: list[Payment]
    total: int
    limit: int
    offset: int


class Refund(ApiModel):
    id: UUID
    payment_id: UUID
    amount: int
    payment_status: PaymentStatus
    refunded_amount: int
    created_at: datetime
