# payments-qa-lab

Test automation portfolio: a layered QA framework, CI pipeline and reporting around a mock payments service.

## Quick start (local)

1. `scripts/make_env.sh` generates a git-ignored `.env` with fresh random credentials
   (JWT secret, admin password, admin TOTP secret, database password). Nothing secret is stored
   in the repository.
2. `docker compose up --build --wait db app provider-mock`
3. `docker compose run --rm tests` (or `docker compose run --rm tests pytest -m smoke`)

Without Docker: create a Postgres database, load `db/init/001_schema.sql`, add `DATABASE_URL`
and `DB_DSN` to `.env` (see `.env.example`), then
`uvicorn app.main:app` and `pytest -m "not quarantine" -n auto tests/api tests/contract`.
