"""Test configuration. Every value can be overridden by an environment variable of the same name
(BASE_URL, DB_DSN, ...) or by a local .env file; defaults match `docker compose up` on localhost."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tests.utils.environment import DEFAULT_ENV, validate_env


class TargetSettings(BaseSettings):
    """Only the environment under test, so collection can decide what to skip without needing
    the credentials the full Settings require."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # local | ci | staging | production (tests/utils/environment.py). Staging and production are
    # read-only: destructive tests are skipped and the HTTP client refuses to change data.
    target_env: str = DEFAULT_ENV

    @field_validator("target_env")
    @classmethod
    def _known_env(cls, value: str) -> str:
        return validate_env(value)


class Settings(TargetSettings):
    base_url: str = "http://localhost:8000"
    # Everything credential-like is required and comes from .env / the environment
    # (scripts/make_env.sh generates them). Nothing secret has a default.
    db_dsn: str
    provider_url: str = "http://localhost:8081"
    # Must equal the app's PROVIDER_TIMEOUT_S (compose sets 2). Integration tests derive their
    # time budget from it: a provider hang may cost timeout + 1 s, never more.
    provider_timeout_s: float = 2.0

    # The app creates this admin at startup from the same variables, so the tests can log in
    # and compute TOTP codes.
    admin_email: str = "admin@lab.test"
    admin_password: str
    admin_totp_secret: str

    # Needed only to forge tokens (expired / wrong-signature) for basic access checks.
    jwt_secret: str

    # Generous on purpose: a slow CI runner must not turn into a flaky test. The app itself
    # answers in milliseconds; anything near this limit is a real hang.
    http_timeout_s: float = 15.0

    # Optional: base URL of the GitHub repo, used to link requirement ids to their issues.
    repo_url: str = ""

    # Where the app writes its JSON request log (the app's LOG_FILE) as seen from the tests; compose
    # mounts the same volume. Empty = the tests/logs tests and the log checks in tests/events skip.
    app_log_file: str = ""
    # The broker the app publishes domain events to. Empty = tests/events skips.
    rabbitmq_url: str = ""
