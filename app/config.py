from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (names are the upper-cased fields)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # No defaults for anything secret: the app must refuse to start without them.
    # See .env.example and scripts/make_env.sh.
    database_url: str
    jwt_secret: str = Field(min_length=32)
    admin_email: str = "admin@lab.test"
    admin_password: str = Field(min_length=8)
    admin_totp_secret: str = Field(min_length=16)
    access_token_ttl_s: int = 3600
    mfa_token_ttl_s: int = 300
    # Cost 4 is the bcrypt minimum: logins cost ~1 ms, so a fresh merchant per test stays cheap.
    # Never do this outside a lab.
    bcrypt_rounds: int = 4

    provider_url: str = "http://localhost:8081"
    # 2 s: long enough for the "slow" provider (1 s) to succeed, short enough that a hung
    # provider cannot hold the payment row lock and the request thread for long.
    provider_timeout_s: float = 2.0

    # Comma list of BUG-1..BUG-4, or "all" (see app/bugs.py); unset means a correct app.
    seeded_bugs: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
