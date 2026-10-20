from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Merchant, User, get_session
from app.errors import ERROR_RESPONSES, ApiError
from app.schemas import MerchantCreate, MerchantOut
from app.security import hash_password, require_admin

router = APIRouter(
    prefix="/merchants",
    tags=["merchants"],
    dependencies=[Depends(require_admin)],
    responses=ERROR_RESPONSES,
)


@router.post("", status_code=201, response_model=MerchantOut)
def create_merchant(body: MerchantCreate, session: Session = Depends(get_session)) -> Merchant:
    merchant = Merchant(name=body.name, email=body.email)
    session.add(merchant)
    try:
        session.flush()
        session.add(
            User(
                email=body.email,
                password_hash=hash_password(body.password),
                role="merchant",
                merchant_id=merchant.id,
            )
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError(409, "email_taken", "A merchant with this email already exists") from None
    return merchant


@router.get("", response_model=list[MerchantOut])
def list_merchants(
    limit: int = Query(100, ge=1, le=500), session: Session = Depends(get_session)
) -> list[Merchant]:
    return list(session.scalars(select(Merchant).order_by(Merchant.created_at.desc()).limit(limit)))


@router.delete("/{merchant_id}", status_code=204)
def delete_merchant(merchant_id: UUID, session: Session = Depends(get_session)) -> Response:
    """Cascades to users, payments, refunds and idempotency keys (used by test cleanup)."""
    merchant = session.get(Merchant, merchant_id)
    if merchant is None:
        raise ApiError(404, "merchant_not_found", "Merchant not found")
    session.delete(merchant)
    session.commit()
    return Response(status_code=204)
