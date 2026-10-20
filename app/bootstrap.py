"""Startup tasks. The admin account is never stored in the repository: it is created (or
brought back in line with the environment) every time the app boots."""

import logging
import time

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.db import User, get_engine
from app.security import hash_password

log = logging.getLogger(__name__)


def ensure_admin(attempts: int = 10, delay_s: float = 1.0) -> None:
    """Idempotent upsert of the admin user from ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_TOTP_SECRET.

    Safe when several workers start at once (ON CONFLICT). Retries briefly because the database
    may still be accepting connections when the app container starts.
    """
    settings = get_settings()
    values = {
        "email": settings.admin_email,
        "password_hash": hash_password(settings.admin_password),
        "role": "admin",
        "merchant_id": None,
        "totp_secret": settings.admin_totp_secret,
    }
    statement = insert(User).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[User.email],
        set_={
            k: statement.excluded[k]
            for k in ("password_hash", "role", "merchant_id", "totp_secret")
        },
    )
    for attempt in range(1, attempts + 1):
        try:
            with get_engine().begin() as conn:
                conn.execute(statement)
            return
        except OperationalError:
            if attempt == attempts:
                raise
            log.warning("database not ready (attempt %d/%d), retrying", attempt, attempts)
            time.sleep(delay_s)
