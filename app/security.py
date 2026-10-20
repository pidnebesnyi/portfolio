from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Merchant, get_session
from app.errors import ApiError

ALGORITHM = "HS256"
Role = Literal["merchant", "admin"]
_bearer = HTTPBearer(auto_error=False, description="JWT from /auth/login (or /auth/2fa for admins)")


def _pw_bytes(password: str) -> bytes:
    # bcrypt only looks at the first 72 bytes (and bcrypt 5 raises on longer input).
    return password.encode()[:72]


def hash_password(password: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt(rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(_pw_bytes(password), password_hash.encode())


def _encode(claims: dict[str, Any], ttl_s: int) -> str:
    payload = {**claims, "exp": datetime.now(UTC) + timedelta(seconds=ttl_s)}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=ALGORITHM)


def create_access_token(user_id: UUID, role: Role, merchant_id: UUID | None) -> str:
    return _encode(
        {
            "sub": str(user_id),
            "role": role,
            "merchant_id": str(merchant_id) if merchant_id else None,
            "typ": "access",
        },
        get_settings().access_token_ttl_s,
    )


def create_mfa_token(user_id: UUID) -> str:
    return _encode({"sub": str(user_id), "typ": "mfa"}, get_settings().mfa_token_ttl_s)


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token, get_settings().jwt_secret, algorithms=[ALGORITHM], options={"require": ["exp"]}
        )
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "token_expired", "Token expired") from None
    except jwt.InvalidTokenError:
        raise ApiError(401, "invalid_token", "Invalid token") from None
    if claims.get("typ") != expected_type:
        raise ApiError(401, "invalid_token", "Wrong token type")
    return claims


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    role: Role
    merchant_id: UUID | None


def principal_from_token(token: str) -> Principal:
    claims = decode_token(token, "access")
    try:
        merchant_id = UUID(claims["merchant_id"]) if claims.get("merchant_id") else None
        return Principal(UUID(claims["sub"]), claims["role"], merchant_id)
    except (KeyError, ValueError):
        raise ApiError(401, "invalid_token", "Malformed claims") from None


def _principal(credentials: HTTPAuthorizationCredentials | None) -> Principal:
    if credentials is None:
        raise ApiError(401, "unauthorized", "Missing bearer token")
    return principal_from_token(credentials.credentials)


def require_merchant(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> Principal:
    principal = _principal(credentials)
    if principal.role != "merchant" or principal.merchant_id is None:
        raise ApiError(403, "forbidden", "Merchant role required")
    # A token can outlive its merchant (test cleanup deletes merchants): unauthenticated.
    if session.scalar(select(Merchant.id).where(Merchant.id == principal.merchant_id)) is None:
        raise ApiError(401, "invalid_token", "Merchant no longer exists")
    return principal


def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    principal = _principal(credentials)
    if principal.role != "admin":
        raise ApiError(403, "forbidden", "Admin role required")
    return principal
