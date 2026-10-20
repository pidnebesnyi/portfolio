"""Minimal server-rendered UI (object under test for the Playwright suite; deliberately plain).

Session = the same JWT the API uses, kept in an HttpOnly, SameSite=Lax cookie. The handlers
reuse the API route functions, so the UI can never disagree with the API about the rules.
Flash messages travel in a one-shot cookie across the post/redirect/get round trip.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import quote, unquote
from uuid import UUID

import pyotp
from fastapi import APIRouter, Cookie, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Merchant, User, get_session
from app.errors import ApiError
from app.routers import payments
from app.schemas import Currency, PaymentCreate, RefundCreate
from app.security import (
    Principal,
    create_access_token,
    create_mfa_token,
    decode_token,
    principal_from_token,
    verify_password,
)
from app.state_machine import PaymentStatus

router = APIRouter(prefix="/ui", include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
templates.env.filters["money"] = lambda minor: f"{minor / 100:.2f}"

SESSION_COOKIE = "session"
MFA_COOKIE = "mfa"
FLASH_COOKIE = "flash"
REFUNDABLE = {PaymentStatus.CAPTURED.value, PaymentStatus.PARTIALLY_REFUNDED.value}


def _redirect(url: str, flash: tuple[str, str] | None = None) -> RedirectResponse:
    response = RedirectResponse(url, status_code=303)
    if flash:
        response.set_cookie(
            FLASH_COOKIE, quote(f"{flash[0]}|{flash[1]}"), path="/ui", httponly=True
        )
    return response


def _render(
    request: Request, name: str, principal: Principal | None = None, **context: object
) -> HTMLResponse:
    flash = None
    if raw := request.cookies.get(FLASH_COOKIE):
        level, _, text = unquote(raw).partition("|")
        flash = {"level": level, "text": text}
    page = templates.TemplateResponse(
        request, name, {"principal": principal, "flash": flash, **context}
    )
    if flash:
        page.delete_cookie(FLASH_COOKIE, path="/ui")
    return page


def _deny(principal: Principal | None) -> RedirectResponse:
    """Pages below are for merchants: anonymous visitors log in, admins go to their landing page."""
    return _redirect("/ui/login" if principal is None else "/ui/payments")


def _start_session(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=get_settings().access_token_ttl_s,
        path="/ui",
        httponly=True,
        samesite="lax",
        # `secure` stays off: the lab runs over plain http on localhost and in CI.
    )


def current_principal(
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Principal | None:
    """None when there is no valid session; handlers then redirect to the login page."""
    if not session_cookie:
        return None
    try:
        return principal_from_token(session_cookie)
    except ApiError:
        return None


# --- login / 2fa -----------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return _render(request, "login.html")


@router.post("/login")
def login(
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: Session = Depends(get_session),
) -> RedirectResponse:
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        return _redirect("/ui/login", ("error", "Invalid email or password"))
    if user.role == "admin":
        response = _redirect("/ui/2fa")
        response.set_cookie(
            MFA_COOKIE,
            create_mfa_token(user.id),
            max_age=get_settings().mfa_token_ttl_s,
            path="/ui",
            httponly=True,
            samesite="lax",
        )
        return response
    response = _redirect("/ui/payments")
    _start_session(response, create_access_token(user.id, "merchant", user.merchant_id))
    return response


@router.get("/2fa", response_class=HTMLResponse)
def two_factor_page(request: Request) -> Response:
    if MFA_COOKIE not in request.cookies:
        return _redirect("/ui/login")
    return _render(request, "two_factor.html")


@router.post("/2fa")
def two_factor(
    code: Annotated[str, Form()],
    mfa_cookie: Annotated[str | None, Cookie(alias=MFA_COOKIE)] = None,
    db: Session = Depends(get_session),
) -> RedirectResponse:
    if not mfa_cookie:
        return _redirect("/ui/login")
    try:
        claims = decode_token(mfa_cookie, "mfa")
    except ApiError:
        return _redirect("/ui/login", ("error", "Verification expired, log in again"))
    user = db.get(User, UUID(claims["sub"]))
    if user is None or user.totp_secret is None:
        return _redirect("/ui/login")
    if not pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
        return _redirect("/ui/2fa", ("error", "Wrong verification code"))
    response = _redirect("/ui/payments")
    _start_session(response, create_access_token(user.id, "admin", None))
    response.delete_cookie(MFA_COOKIE, path="/ui")
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = _redirect("/ui/login")
    response.delete_cookie(SESSION_COOKIE, path="/ui")
    return response


# --- payments --------------------------------------------------------------------------------


def _day_bound(value: str, *, end: bool) -> datetime | None:
    """`YYYY-MM-DD` from a date input -> first/last instant of that day in UTC."""
    if not value:
        return None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return None
    if end:
        return (
            datetime.combine(day + timedelta(days=1), time.min, tzinfo=UTC) - timedelta.resolution
        )
    return datetime.combine(day, time.min, tzinfo=UTC)


def _status_or_none(value: str) -> PaymentStatus | None:
    try:
        return PaymentStatus(value)
    except ValueError:
        return None


@router.get("")
def root() -> RedirectResponse:
    return _redirect("/ui/payments")


@router.get("/payments", response_class=HTMLResponse)
def payments_page(
    request: Request,
    status: str = "",
    created_from: str = "",
    created_to: str = "",
    principal: Principal | None = Depends(current_principal),
    db: Session = Depends(get_session),
) -> Response:
    if principal is None:
        return _redirect("/ui/login")
    if principal.role == "admin":
        merchants = db.scalars(select(Merchant).order_by(Merchant.created_at.desc()).limit(50))
        return _render(request, "admin.html", principal, merchants=list(merchants))
    page = payments.list_payments(
        status=_status_or_none(status),
        created_from=_day_bound(created_from, end=False),
        created_to=_day_bound(created_to, end=True),
        limit=100,
        offset=0,
        principal=principal,
        session=db,
    )
    return _render(
        request,
        "payments.html",
        principal,
        page=page,
        statuses=[s.value for s in PaymentStatus],
        filters={"status": status, "created_from": created_from, "created_to": created_to},
    )


@router.get("/payments/new", response_class=HTMLResponse)
def new_payment_page(
    request: Request, principal: Principal | None = Depends(current_principal)
) -> Response:
    if principal is None or principal.role == "admin":
        return _deny(principal)
    # One key per rendered form: a double click or a resubmit replays instead of paying twice.
    return _render(
        request,
        "payment_new.html",
        principal,
        currencies=[c.value for c in Currency],
        idempotency_key=str(uuid.uuid4()),
    )


@router.post("/payments/new")
def create_payment(
    amount: Annotated[str, Form()],
    currency: Annotated[str, Form()],
    card_token: Annotated[str, Form()],
    idempotency_key: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    principal: Principal | None = Depends(current_principal),
    db: Session = Depends(get_session),
) -> RedirectResponse:
    if principal is None or principal.role == "admin":
        return _deny(principal)
    try:
        body = PaymentCreate.model_validate(
            {
                "amount": int(amount),
                "currency": currency,
                "description": description,
                "card_token": card_token,
            }
        )
        payment = payments.create_payment(
            body, Response(), idempotency_key, principal=principal, session=db
        )
    except (ValueError, ApiError):
        return _redirect("/ui/payments/new", ("error", "Check the amount, currency and card token"))
    return _redirect(f"/ui/payments/{payment.id}", ("success", "Payment created"))


@router.get("/payments/{payment_id}", response_class=HTMLResponse)
def payment_page(
    request: Request,
    payment_id: UUID,
    principal: Principal | None = Depends(current_principal),
    db: Session = Depends(get_session),
) -> Response:
    if principal is None or principal.role == "admin":
        return _deny(principal)
    try:
        payment = payments.get_payment(payment_id, principal=principal, session=db)
    except ApiError:
        return _redirect("/ui/payments", ("error", "Payment not found"))
    return _render(
        request,
        "payment_detail.html",
        principal,
        payment=payment,
        refundable=payment.status in REFUNDABLE,
        remaining=payment.amount - payment.refunded_amount,
    )


@router.post("/payments/{payment_id}/refund")
def refund(
    payment_id: UUID,
    amount: Annotated[str, Form()],
    principal: Principal | None = Depends(current_principal),
    db: Session = Depends(get_session),
) -> RedirectResponse:
    if principal is None or principal.role == "admin":
        return _deny(principal)
    target = f"/ui/payments/{payment_id}"
    try:
        body = RefundCreate.model_validate({"amount": int(amount)})
        payments.refund_payment(payment_id, body, principal=principal, session=db)
    except ValueError:
        return _redirect(target, ("error", "Enter the refund amount in minor units"))
    except ApiError as exc:
        return _redirect(target, ("error", exc.body["message"] or exc.body["code"]))
    return _redirect(target, ("success", "Refund created"))
