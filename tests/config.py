"""Test configuration. Every value can be overridden by an environment variable of the same name
(BASE_URL, DB_DSN, ...) or by a local .env file; defaults match `docker compose up` on localhost."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    # Optional: base URL of the GitHub repo, used to turn requirement ids into Allure links.
    repo_url: str = ""
