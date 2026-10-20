# payments-qa-lab

A QA automation portfolio: a layered test framework, a CI pipeline and published reports.
The object under test is a mock payments service (FastAPI + Postgres: merchants, payments, refunds)
with a provider mock behind it; the product is the framework, the pipeline and the reports.

[![PR](https://github.com/pidnebesnyi/portfolio/actions/workflows/pr.yml/badge.svg)](https://github.com/pidnebesnyi/portfolio/actions/workflows/pr.yml)
[![Nightly](https://github.com/pidnebesnyi/portfolio/actions/workflows/nightly.yml/badge.svg)](https://github.com/pidnebesnyi/portfolio/actions/workflows/nightly.yml)
[![Load](https://github.com/pidnebesnyi/portfolio/actions/workflows/load.yml/badge.svg)](https://github.com/pidnebesnyi/portfolio/actions/workflows/load.yml)

## Live reports

- Landing page with the latest numbers: https://pidnebesnyi.github.io/portfolio/
- Allure report (merged nightly, with history): https://pidnebesnyi.github.io/portfolio/report/
- Load report: https://pidnebesnyi.github.io/portfolio/load/

## Architecture

```
tests, locust --HTTP--> app --SQL--> db
                         |
                         +--HTTP--> provider-mock
                         +--AMQP--> rabbitmq (payments.events)
                         +--file--> app log (shared volume, read by tests)
tests <--AMQP-- rabbitmq
tests -------------SQL (direct checks)-----------> db
```

The provider mock chooses its behaviour per request from the `card_token`: `tok_success`,
`tok_decline`, `tok_error`, `tok_timeout` or `tok_slow`. Parallel tests never share provider state.

## Run it

```bash
scripts/make_env.sh
docker compose up --build --wait db app provider-mock
docker compose run --rm tests
```

Smoke tests only: `docker compose run --rm tests pytest -m smoke`

Load test (1 minute by default in compose; CI runs 3 minutes):

```bash
mkdir -m 777 load-report && docker compose --profile load run --rm locust
```

Credentials include a RabbitMQ password; an `.env` made before it existed needs `scripts/make_env.sh --force`.

Without Docker: create a Postgres database, load `db/init/001_schema.sql`, set `DATABASE_URL` and
`DB_DSN` in `.env` (see `.env.example`), run `uvicorn app.main:app`, then
`pytest -n auto`. The log and event tests need `LOG_FILE` (app) and `APP_LOG_FILE` (tests) pointing at one file and `RABBITMQ_URL` pointing at a broker (see `.env.example`); without them they skip. Browser tests also need `playwright install chromium`.

Credentials are generated per run by `scripts/make_env.sh` and written to the git-ignored `.env`.
Nothing secret is in the repository. CI generates and masks them the same way, and the repository
needs zero secrets.

## Test layers

| Folder | What | Count | Gate |
|---|---|---:|---|
| `tests/api` | REST behaviour: payments, refunds, idempotency, transitions, access | 90 | PR (`api` job); nightly |
| `tests/integration` | Payment flow against the provider mock: decline, error, timeout | 8 | PR (`api` job); nightly |
| `tests/db` | SQL invariants (JOIN, GROUP BY / HAVING, window, CTE) on data created through the API | 6 | PR (`api` job); nightly |
| `tests/ui` | Playwright through page objects; data comes from the API; includes network interception (`page.route`) and computed-style checks | 32 (6 smoke) | PR (`ui-smoke` job, smoke only); nightly |
| `tests/logs` | The app's JSON request log: request ids, domain events, no secrets | 11 (2 smoke) | PR (`api` job); nightly |
| `tests/events` | Domain events consumed from RabbitMQ: captured, refunded, failed, nothing for rejected requests | 5 (1 smoke) | PR (`api` job); nightly |
| `tests/unit` | Landing-page builder, Allure suite labels | 19 | PR (`api` job); nightly |

About 171 tests in total, 22 of them tagged `smoke`.

## Pipeline

| Workflow | Trigger | What | Publishes |
|---|---|---|---|
| `pr.yml` | every pull request | lint (ruff); `api` job (unit, API, integration and DB tests on compose); `ui-smoke` job (browser smoke tests). Each job has a 10-minute timeout | Allure results and UI traces as workflow artifacts |
| `nightly.yml` | 02:30 UTC daily, manual | full suite in one job (pytest-xdist); Allure report with history | `/report/` and the landing-page numbers at the site root |
| `load.yml` | Mondays 04:00 UTC, manual | Locust, 20 users for 3 minutes; fails on p95 > 500 ms or errors > 1 % | `/load/` |

## Framework decisions

- The app logs one JSON line per request and per domain event with a request id, and publishes
  events to RabbitMQ after the commit; both are checked as evidence (`tests/logs`, `tests/events`).
- Each test creates its own merchant through the API and deletes it at teardown, so tests run in
  parallel (`pytest-xdist`) without ordering rules.
- API clients are typed, and responses are parsed into Pydantic models.
- Configuration is loaded with pydantic-settings.
- Markers are enforced: every test has exactly one of `smoke` or `regression`, and
  `--strict-markers` fails on typos. Retries happen only through `@pytest.mark.flaky` with a reason.
- A failed test keeps evidence in Allure: last request and response, last SQL, and for UI tests a
  screenshot, trace and video. Credentials are masked.
- UI tests get their data from the API and verify only what the UI shows.

## Read next

[`docs/test-strategy.md`](docs/test-strategy.md): what is tested at which level and why, the data
and flakiness policies, and what is deliberately not automated.
