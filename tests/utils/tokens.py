"""Forge JWTs for basic access checks (expired, wrongly signed, wrong type)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pyotp


def forge_token(
    secret: str,
    *,
    user_id: UUID,
    role: str = "merchant",
    merchant_id: UUID | None,
    expires_in_s: int = 3600,
    token_type: str = "access",
) -> str:
    claims = {
        "sub": str(user_id),
        "role": role,
        "merchant_id": str(merchant_id) if merchant_id else None,
        "typ": token_type,
        "exp": datetime.now(UTC) + timedelta(seconds=expires_in_s),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def decode_unverified(token: str) -> dict[str, object]:
    """Read claims without checking the signature or expiry (we only inspect, never trust)."""
    return jwt.decode(token, options={"verify_signature": False, "verify_exp": False})


def totp_code(secret: str) -> str:
    return pyotp.TOTP(secret).now()
