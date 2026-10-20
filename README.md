# payments-qa-lab

A QA automation portfolio: a layered test framework, a CI pipeline and published reports.
The object under test is a mock payments service (FastAPI + Postgres: merchants, payments, refunds)
with a provider mock behind it; the product is the framework, the pipeline and the reports.

[![PR](https://github.com/pidnebesnyi/portfolio/actions/workflows/pr.yml/badge.svg)](https://github.com/pidnebesnyi/portfolio/actions/workflows/pr.yml)
[![Nightly](https://github.com/pidnebesnyi/portfolio/actions/workflows/nightly.yml/badge.svg)](https://github.com/pidnebesnyi/portfolio/actions/workflows/nightly.yml)
[![Seeded bugs](https://github.com/pidnebesnyi/portfolio/actions/workflows/seeded-bugs.yml/badge.svg)](https://github.com/pidnebesnyi/portfolio/actions/workflows/seeded-bugs.yml)
[![Load](https://github.com/pidnebesnyi/portfolio/actions/workflows/load.yml/badge.svg)](https://github.com/pidnebesnyi/portfolio/actions/workflows/load.yml)

## Live reports

- Landing page with the latest numbers: https://pidnebesnyi.github.io/portfolio/
- Allure report (merged nightly, with history): https://pidnebesnyi.github.io/portfolio/report/
- Seeded bugs: https://pidnebesnyi.github.io/portfolio/bugs/
- Load report: https://pidnebesnyi.github.io/portfolio/load/

## Architecture

```
tests, locust --HTTP--> app --SQL--> db
                         |
                         +--HTTP--> provider-mock
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

Without Docker: create a Postgres database, load `db/init/001_schema.sql`, set `DATABASE_URL` and
`DB_DSN` in `.env` (see `.env.example`), run `uvicorn app.main:app`, then
`pytest -m "not quarantine" -n auto`. Browser tests also need `playwright install chromium`.

Credentials are generated per run by `scripts/make_env.sh` and written to the git-ignored `.env`.
Nothing secret is in the repository. CI generates and masks them the same way, and the repository
needs zero secrets.

## Test layers

| Folder | What | Count | Gate |
|---|---|---:|---|
| `tests/api` | REST behaviour: payments, refunds, idempotency, transitions, access | 95 | PR (`api` job); nightly |
| `tests/contract` | Schemathesis requests generated from `/openapi.json`, 13 operations as subtests | 1 | PR (`api` job); nightly |
| `tests/integration` | Payment flow against the provider mock: decline, error, timeout | 8 | PR (`api` job); nightly |
| `tests/db` | SQL invariants (JOIN, GROUP BY / HAVING, window, CTE) on data created through the API | 7 | PR (`api` job); nightly |
| `tests/ui` | Playwright through page objects; data comes from the API | 21 (4 smoke) | PR (`ui-smoke` job, smoke only); nightly |
| `tests/unit` | Landing-page builder (`scripts/build_site.py`) | 13 | nightly |

About 145 tests in total, 17 of them tagged `smoke`.

## Pipeline

| Workflow | Trigger | What | Publishes |
|---|---|---|---|
| `pr.yml` | every pull request | lint (gitleaks, ruff, mypy); `api` job (API, integration, DB and contract tests on compose); `ui-smoke` job (browser smoke tests). Each job has a 10-minute timeout | Allure results and UI traces as workflow artifacts |
| `nightly.yml` | 02:30 UTC daily, manual | full suite in 3 pytest-split shards; one merged Allure report with history | `/report/` and the landing-page numbers at the site root |
| `seeded-bugs.yml` | Mondays 05:00 UTC, manual | each of BUG-1..4 switched on in turn; a marked test must fail for each. Latest run: 4 seeded, 4 caught | `/bugs/` |
| `load.yml` | Mondays 04:00 UTC, manual | Locust, 20 users for 3 minutes; fails on p95 > 500 ms or errors > 1 % | `/load/` |

## Seeded bugs

The `SEEDED_BUGS` environment variable switches on known defects in the app: BUG-1 creates a second
payment on an idempotent replay, BUG-2 removes the over-refund guard, BUG-3 lets a merchant read
another merchant's payment, and BUG-4 leaves a payment `authorized` after a provider timeout.
The weekly job passes only if a marked test fails for each bug and the suite is green with no bug on.
Results are at https://pidnebesnyi.github.io/portfolio/bugs/.

## Framework decisions

- Each test creates its own merchant through the API and deletes it at teardown, so tests run in
  parallel (`pytest-xdist`) and in shards without ordering rules.
- API clients are typed, and responses are parsed into Pydantic models.
- Configuration is loaded with pydantic-settings.
- Markers are enforced: every test has exactly one of `smoke`, `regression` or `quarantine`, and
  `--strict-markers` fails on typos. Retries happen only through `@pytest.mark.flaky` with a reason.
- A failed test keeps evidence in Allure: last request and response, last SQL, and for UI tests a
  screenshot, trace and video. Credentials are masked.
- UI tests get their data from the API and verify only what the UI shows.

## Read next

[`docs/test-strategy.md`](docs/test-strategy.md): what is tested at which level and why, the data
and flakiness policies, and what is deliberately not automated.
