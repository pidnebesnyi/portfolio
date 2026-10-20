from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field

from app.state_machine import PaymentStatus


def _no_nul(value: str) -> str:
    # Postgres text cannot hold NUL; reject it as a validation error instead of a 500.
    if "\x00" in value:
        raise ValueError("NUL character is not allowed")
    return value


Text = Annotated[str, AfterValidator(_no_nul)]


class Currency(StrEnum):
    UAH = "UAH"
    USD = "USD"
    EUR = "EUR"


# --- auth ---------------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: Text = Field(min_length=1, max_length=255)
    password: Text = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    """Merchant: access_token + token_type. Admin: mfa_required + mfa_token, then /auth/2fa."""

    access_token: str | None = None
    token_type: str | None = None
    mfa_required: bool | None = None
    mfa_token: str | None = None


class TwoFactorRequest(BaseModel):
    mfa_token: Text = Field(min_length=1, max_length=2048)
    code: Text = Field(min_length=1, max_length=16)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


# --- merchants ----------------------------------------------------------------------------


class MerchantCreate(BaseModel):
    name: Text = Field(min_length=1, max_length=100)
    email: Text = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    password: Text = Field(min_length=8, max_length=72)


class MerchantOut(BaseModel):
    id: UUID
    name: str
    email: str
    created_at: datetime


# --- payments -----------------------------------------------------------------------------

MAX_AMOUNT = 100_000_000  # 1,000,000.00; keeps sums far inside the integer column


class PaymentCreate(BaseModel):
    amount: int = Field(
        strict=True, gt=0, le=MAX_AMOUNT, description="Minor units, e.g. 1050 = 10.50"
    )
    currency: Currency
    description: Text = Field(default="", max_length=255)
    card_token: Text = Field(min_length=1, max_length=64)


class PaymentOut(BaseModel):
    id: UUID
    merchant_id: UUID
    amount: int
    currency: Currency
    description: str
    card_token: str
    status: PaymentStatus
    failure_reason: str | None = None
    refunded_amount: int
    created_at: datetime
    updated_at: datetime


class PaymentList(BaseModel):
    items: list[PaymentOut]
    total: int
    limit: int
    offset: int


class RefundCreate(BaseModel):
    amount: int = Field(strict=True, gt=0, le=MAX_AMOUNT, description="Minor units")


class RefundOut(BaseModel):
    id: UUID
    payment_id: UUID
    amount: int
    payment_status: PaymentStatus
    refunded_amount: int
    created_at: datetime
