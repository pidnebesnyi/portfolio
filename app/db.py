from collections.abc import Iterator
from datetime import UTC, datetime
from functools import lru_cache
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str]
    email: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str]
    password_hash: Mapped[str]
    role: Mapped[str]
    merchant_id: Mapped[UUID | None] = mapped_column(ForeignKey("merchants.id"))
    totp_secret: Mapped[str | None]


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    merchant_id: Mapped[UUID] = mapped_column(ForeignKey("merchants.id"))
    amount: Mapped[int]
    currency: Mapped[str]
    description: Mapped[str]
    card_token: Mapped[str]
    status: Mapped[str]
    failure_reason: Mapped[str | None]
    refunded_amount: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("payments.id"))
    amount: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=_now)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str]
    merchant_id: Mapped[UUID] = mapped_column(ForeignKey("merchants.id"))
    request_hash: Mapped[str]
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("payments.id"))
    created_at: Mapped[datetime] = mapped_column(default=_now)


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url, pool_size=10, max_overflow=20, pool_pre_ping=True
    )


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request; writes commit explicitly in the handlers."""
    with _session_factory()() as session:
        yield session
