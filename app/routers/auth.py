from functools import lru_cache
from uuid import UUID

import pyotp
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import User, get_session
from app.errors import ERROR_RESPONSES, ApiError
from app.schemas import LoginRequest, LoginResponse, TokenResponse, TwoFactorRequest
from app.security import (
    create_access_token,
    create_mfa_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"], responses=ERROR_RESPONSES)


# Verified against when the email is unknown, so response time does not reveal which emails exist.
@lru_cache
def _dummy_hash() -> str:
    return hash_password("not-a-real-password")


@router.post("/login", response_model=LoginResponse, response_model_exclude_none=True)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    """Merchants get an access token. Admins get an MFA token and must call /auth/2fa."""
    user = session.scalar(select(User).where(User.email == body.email))
    if user is None:
        verify_password(body.password, _dummy_hash())
        raise ApiError(401, "invalid_credentials", "Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "Invalid email or password")
    if user.role == "admin":
        return LoginResponse(mfa_required=True, mfa_token=create_mfa_token(user.id))
    return LoginResponse(
        access_token=create_access_token(user.id, "merchant", user.merchant_id),
        token_type="bearer",
    )


@router.post("/2fa", response_model=TokenResponse)
def second_factor(body: TwoFactorRequest, session: Session = Depends(get_session)) -> TokenResponse:
    claims = decode_token(body.mfa_token, "mfa")
    try:
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError):
        raise ApiError(401, "invalid_token", "Malformed claims") from None
    user = session.get(User, user_id)
    if user is None or user.totp_secret is None:
        raise ApiError(401, "invalid_token", "Unknown user")
    # valid_window=1 tolerates one 30 s step of clock drift between the test runner and the app.
    if not pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1):
        raise ApiError(401, "invalid_code", "Wrong verification code")
    return TokenResponse(access_token=create_access_token(user.id, "admin", None))
