import hashlib
import json
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import IdempotencyKey, Payment, Refund, get_session
from app.errors import ERROR_RESPONSES, ApiError
from app.provider import ChargeOutcome, ProviderClient, get_provider
from app.schemas import PaymentCreate, PaymentList, PaymentOut, RefundCreate, RefundOut
from app.security import Principal, require_merchant
from app.state_machine import Action, PaymentStatus, can

router = APIRouter(prefix="/payments", tags=["payments"], responses=ERROR_RESPONSES)

IdempotencyKeyHeader = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        description="Required. Same key + same body replays the first result (200 + "
        "`Idempotent-Replayed: true`); same key + different body is a 409.",
    ),
]


def _request_hash(body: PaymentCreate) -> str:
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _merchant_id(principal: Principal) -> UUID:
    assert principal.merchant_id is not None  # guaranteed by require_merchant
    return principal.merchant_id


def _get_for_update(session: Session, payment_id: UUID, merchant_id: UUID) -> Payment:
    """Load an own payment and lock its row until commit.

    Another merchant's payment is a 404, not a 403, so existence is not leaked.
    """
    payment = session.scalar(
        select(Payment)
        .where(Payment.id == payment_id, Payment.merchant_id == merchant_id)
        .with_for_update()
    )
    if payment is None:
        raise ApiError(404, "payment_not_found", "Payment not found")
    return payment


def _require_transition(payment: Payment, action: Action) -> None:
    status = PaymentStatus(payment.status)
    if not can(action, status):
        raise ApiError(
            409,
            "invalid_transition",
            f"Cannot {action} a payment in status {status}",
            **{"from": status.value, "action": action.value},
        )


@router.post(
    "",
    status_code=201,
    response_model=PaymentOut,
    responses={
        200: {"model": PaymentOut, "description": "Idempotent replay of an earlier request"}
    },
)
def create_payment(
    body: PaymentCreate,
    response: Response,
    idempotency_key: IdempotencyKeyHeader,
    principal: Principal = Depends(require_merchant),
    session: Session = Depends(get_session),
) -> Payment:
    merchant_id = _merchant_id(principal)
    request_hash = _request_hash(body)

    def replay() -> Payment | None:
        existing = session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.key == idempotency_key, IdempotencyKey.merchant_id == merchant_id
            )
        )
        if existing is None:
            return None
        if existing.request_hash != request_hash:
            raise ApiError(
                409, "idempotency_key_reused", "Idempotency-Key was used with a different body"
            )
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
        return session.get_one(Payment, existing.payment_id)

    if (replayed := replay()) is not None:
        return replayed

    payment = Payment(
        merchant_id=merchant_id,
        amount=body.amount,
        currency=body.currency.value,
        description=body.description,
        card_token=body.card_token,
        status=PaymentStatus.CREATED.value,
    )
    session.add(payment)
    session.flush()
    session.add(
        IdempotencyKey(
            key=idempotency_key,
            merchant_id=merchant_id,
            request_hash=request_hash,
            payment_id=payment.id,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        # Two requests with the same key raced; the unique (key, merchant_id) constraint picked
        # the winner. Roll back our payment and answer with the winner's.
        session.rollback()
        if (replayed := replay()) is not None:
            return replayed
        raise
    return payment


@router.get("", response_model=PaymentList)
def list_payments(
    status: PaymentStatus | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
    principal: Principal = Depends(require_merchant),
    session: Session = Depends(get_session),
) -> PaymentList:
    conditions = [Payment.merchant_id == _merchant_id(principal)]
    if status is not None:
        conditions.append(Payment.status == status.value)
    if created_from is not None:
        conditions.append(Payment.created_at >= created_from)
    if created_to is not None:
        conditions.append(Payment.created_at <= created_to)
    total = session.scalar(select(func.count()).select_from(Payment).where(*conditions)) or 0
    rows = session.scalars(
        select(Payment)
        .where(*conditions)
        .order_by(Payment.created_at.desc(), Payment.id)
        .limit(limit)
        .offset(offset)
    )
    return PaymentList(
        items=[PaymentOut.model_validate(p, from_attributes=True) for p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: UUID,
    principal: Principal = Depends(require_merchant),
    session: Session = Depends(get_session),
) -> Payment:
    conditions = [Payment.id == payment_id, Payment.merchant_id == _merchant_id(principal)]
    payment = session.scalar(select(Payment).where(*conditions))
    if payment is None:
        raise ApiError(404, "payment_not_found", "Payment not found")
    return payment


@router.post("/{payment_id}/authorize", response_model=PaymentOut)
def authorize_payment(
    payment_id: UUID,
    principal: Principal = Depends(require_merchant),
    session: Session = Depends(get_session),
    provider: ProviderClient = Depends(get_provider),
) -> Payment:
    """Charge via the provider. The outcome is always final: authorized or failed, never pending."""
    payment = _get_for_update(session, payment_id, _merchant_id(principal))
    _require_transition(payment, Action.AUTHORIZE)
    # The row lock is held during the provider call on purpose: a concurrent authorize of the
    # same payment waits, then sees the new status and gets a 409 instead of double-charging.
    result = provider.charge(
        payment.amount, payment.currency, payment.card_token, reference=str(payment.id)
    )
    match result.outcome:
        case ChargeOutcome.APPROVED:
            payment.status = PaymentStatus.AUTHORIZED.value
        case ChargeOutcome.DECLINED:
            payment.status = PaymentStatus.FAILED.value
            payment.failure_reason = "declined"
        case ChargeOutcome.TIMEOUT:
            payment.status = PaymentStatus.FAILED.value
            payment.failure_reason = "provider_timeout"
        case ChargeOutcome.ERROR:
            payment.status = PaymentStatus.FAILED.value
            payment.failure_reason = "provider_error"
    session.commit()
    return payment


@router.post("/{payment_id}/capture", response_model=PaymentOut)
def capture_payment(
    payment_id: UUID,
    principal: Principal = Depends(require_merchant),
    session: Session = Depends(get_session),
) -> Payment:
    payment = _get_for_update(session, payment_id, _merchant_id(principal))
    _require_transition(payment, Action.CAPTURE)
    payment.status = PaymentStatus.CAPTURED.value
    session.commit()
    return payment


@router.post("/{payment_id}/void", response_model=PaymentOut)
def void_payment(
    payment_id: UUID,
    principal: Principal = Depends(require_merchant),
    session: Session = Depends(get_session),
) -> Payment:
    payment = _get_for_update(session, payment_id, _merchant_id(principal))
    _require_transition(payment, Action.VOID)
    payment.status = PaymentStatus.VOIDED.value
    session.commit()
    return payment


@router.post("/{payment_id}/refunds", status_code=201, response_model=RefundOut)
def refund_payment(
    payment_id: UUID,
    body: RefundCreate,
    principal: Principal = Depends(require_merchant),
    session: Session = Depends(get_session),
) -> RefundOut:
    # SELECT ... FOR UPDATE serialises concurrent refunds of one payment: the second request
    # blocks here, then re-reads refunded_amount and is checked against the true remainder.
    payment = _get_for_update(session, payment_id, _merchant_id(principal))
    _require_transition(payment, Action.REFUND)
    refundable = payment.amount - payment.refunded_amount
    if body.amount > refundable:
        raise ApiError(
            422,
            "refund_exceeds_amount",
            f"Refund of {body.amount} exceeds the refundable {refundable}",
            refundable=refundable,
        )
    refund = Refund(payment_id=payment.id, amount=body.amount)
    session.add(refund)
    payment.refunded_amount += body.amount
    payment.status = (
        PaymentStatus.REFUNDED
        if payment.refunded_amount == payment.amount
        else PaymentStatus.PARTIALLY_REFUNDED
    ).value
    session.commit()
    return RefundOut(
        id=refund.id,
        payment_id=payment.id,
        amount=refund.amount,
        payment_status=PaymentStatus(payment.status),
        refunded_amount=payment.refunded_amount,
        created_at=refund.created_at,
    )
