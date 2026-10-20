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
`uvicorn app.main:app` and `pytest -m "not quarantine" -n auto`. Browser tests also need
`playwright install chromium` once (the tests image already has it).

## Test layers

| Folder | What | Notes |
|---|---|---|
| `tests/api`, `tests/contract` | REST behaviour, Schemathesis against `/openapi.json` | PR gate |
| `tests/db` | SQL invariants (JOIN, GROUP BY / HAVING, window, CTE) on data created through the API | every query and result is attached to Allure |
| `tests/ui` | Playwright through page objects in `tests/pages`; data comes from the API | `pytest -m "smoke and ui"` is the PR gate |

A failed test carries its last request/response, last SQL and, for UI tests, screenshot, trace and
video in the Allure result. The nightly workflow runs everything in 3 shards and publishes the
report to https://pidnebesnyi.github.io/portfolio/report/ (history kept between runs).
