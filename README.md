# Test Automation Lab

A QA automation portfolio: one pytest framework that covers many kinds of testing, a CI pipeline
and published reports. REST API checks against the service's own OpenAPI contract, SQL verification, Playwright UI tests (page objects,
network interception, computed styles), RabbitMQ events, structured log checks, WireMock service
stubs, Gherkin scenarios readable without code (pytest-bdd), a Postman collection run by Newman, and a Locust load test, all running in Docker and GitHub Actions.

The system under test is a small demo service (FastAPI + Postgres; payments is the example domain:
merchants, payments, refunds). The domain is only the subject: the product is the framework, the
pipeline and the reports.

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
                         +--HTTP--> provider-mock (WireMock)
                         +--AMQP--> rabbitmq (payments.events)
                         +--file--> app log (shared volume, read by tests)
tests <--AMQP-- rabbitmq
tests -------------SQL (direct checks)-----------> db
tests --HTTP (admin API: sent charges)--> provider-mock
```

The provider stub is [WireMock](https://wiremock.org/) with one JSON mapping per behaviour in
`provider-mock/mappings`. It chooses the response from the `card_token` in the request body:
`tok_success` (and any unknown token) approves, `tok_decline` declines, `tok_error` answers HTTP 500,
`tok_slow` approves after 1 s and `tok_timeout` after 10 s, past the app's 2 s timeout. The tests
ask WireMock's admin API (`/__admin/requests/find`) which charges carry a given payment id, so
parallel tests never share provider state.

## Run it

```bash
scripts/make_env.sh
docker compose up --build --wait db app provider-mock
docker compose run --rm tests
```

Smoke tests only: `docker compose run --rm tests pytest -m smoke`

Postman collection through Newman (how to open it in Postman: [`postman/README.md`](postman/README.md)):

```bash
docker compose --profile postman run --rm newman
```

Load test (1 minute by default in compose; CI runs 3 minutes):

```bash
mkdir -m 777 load-report && docker compose --profile load run --rm locust
```

Credentials include a RabbitMQ password; an `.env` made before it existed needs `scripts/make_env.sh --force`.

Without Docker: create a Postgres database, load `db/init/001_schema.sql`, set `DATABASE_URL` and
`DB_DSN` in `.env` (see `.env.example`), start the provider stub with
`java -jar wiremock-standalone-3.13.2.jar --port 8081 --root-dir provider-mock`, run
`uvicorn app.main:app`, then `pytest -n auto`. The 11 log tests need only `LOG_FILE` (app) and `APP_LOG_FILE` (tests) pointing at one file; the 5 event tests also need `RABBITMQ_URL` pointing at a broker (see `.env.example`). Without them they skip, so a run without Docker and without a broker shows 5 skipped event tests and nothing else. Browser tests also need `playwright install chromium`.

Credentials are generated per run by `scripts/make_env.sh` and written to the git-ignored `.env`.
Nothing secret is in the repository. CI generates and masks them the same way, and the repository
needs zero secrets.

## Test layers

| Folder | What | Count | Gate |
|---|---|---:|---|
| `tests/api` | REST behaviour: payments, refunds, idempotency, transitions, access; input limits, token edge cases and requests sent in parallel (row locks, idempotency races) | 160 | PR (`api` job); nightly |
| `tests/contract` | The published OpenAPI document compared with the pinned one in `tests/contract/openapi.json` | 1 | PR (`api` job); nightly |
| `tests/integration` | Payment flow against the WireMock provider stub: decline, error, timeout, two parallel authorizations | 9 | PR (`api` job); nightly |
| `tests/db` | SQL invariants (JOIN, GROUP BY / HAVING, window, CTE) on data created through the API | 6 | PR (`api` job); nightly |
| `tests/ui` | Playwright through page objects; data comes from the API; includes network interception (`page.route`) and computed-style checks; navigation, redirects and who may open which page, list and form edge cases | 69 (6 smoke) | PR (`ui-smoke` job, smoke only); nightly |
| `tests/logs` | The app's JSON request log: request ids, domain events, no secrets | 11 (2 smoke) | PR (`api` job); nightly |
| `tests/events` | Domain events consumed from RabbitMQ: captured, refunded, failed, nothing for rejected requests | 5 (1 smoke) | PR (`api` job); nightly |
| `tests/bdd` | Business scenarios in Gherkin (`features/*.feature`) that run on the same clients, factories and page objects; one is a browser scenario | 9 | PR (`api` job, all but the browser scenario); nightly |
| `tests/unit` | Landing-page builder, Allure suite labels, the OpenAPI checker, the requirement trace | 49 | PR (`api` job); nightly |

About 319 tests in total, 22 of them tagged `smoke`. Outside pytest: the Postman collection in
`postman/` (20 requests, 59 assertions; PR `api` job) and the Locust profile in `load/`.

## Pipeline

| Workflow | Trigger | What | Publishes |
|---|---|---|---|
| `pr.yml` | every pull request | lint (ruff); `api` job (unit, API, contract, integration, DB, log, event and Gherkin API scenarios on compose, then the Postman collection through Newman); `ui-smoke` job (browser smoke tests). Each job has a 10-minute timeout | Allure results and UI traces as workflow artifacts |
| `nightly.yml` | 02:30 UTC daily; manual runs take `path`, `markers` and `workers` inputs (publish only with `publish` set) | full suite in one job (pytest-xdist); Allure report with history | `/report/` and the landing-page numbers at the site root (scheduled runs, or manual runs with `publish`) |
| `load.yml` | Mondays 04:00 UTC, manual | Locust, 20 users for 3 minutes; fails on p95 > 500 ms or errors > 1 % | `/load/` |

## Suite timing

Measured, not estimated. Full suite (171 tests) on the compose stack, Apple M2 with a 4-CPU Docker
VM, 2026-10-20. The time is pytest's own total; each row is the median of three runs.

| Run | Time | vs serial |
|---|---:|---:|
| serial | 20.0 s | |
| `-n 2` | 14.2 s | −29 % |
| `-n auto` (4 workers) | 13.0 s | −35 % |
| `-n 8` (one run) | 16.2 s | −19 % |

- More workers than CPUs is slower: every worker starts its own browser and they compete for the
  same cores. `-n auto` matches the CPU count, so the nightly and PR `api` jobs use it.
- Where the serial time goes (setup + call + teardown, from `--durations=0`): UI 10.4 s,
  integration 5.7 s, API 4.2 s, DB 1.3 s, events, logs and unit 1.2 s together.
- The three slowest tests are deliberate waits: two provider timeouts at 2.0 s each (the app's
  timeout) and a slow provider at 1.1 s. That wait is the behaviour under test, so they stay;
  xdist spreads them across workers.
- Keeping trace and video for failed UI tests costs about 1.8 s per serial UI run (9.4 s against
  7.6 s with both off), roughly 20 % of UI time. It stays on: a failure without evidence costs more.
- In CI (GitHub-hosted runner, `-n auto`) the nightly full suite takes 21.6 s, the PR `api` job
  (139 tests) 6.6 s and `ui-smoke` (6 tests) 4.9 s.

Reproduce:

```bash
docker compose run --rm tests pytest -q                     # serial
docker compose run --rm tests pytest -q -n auto             # parallel
docker compose run --rm tests pytest -q --durations=15      # slowest tests
docker compose run --rm tests pytest -q tests/ui --video=off --tracing=off   # cost of evidence
```

## Framework decisions

- The app logs one JSON line per request and per domain event with a request id, and publishes
  events to RabbitMQ after the commit; both are checked as evidence (`tests/logs`, `tests/events`).
- Each test creates its own merchant through the API and deletes it at teardown, so tests run in
  parallel (`pytest-xdist`) without ordering rules.
- API clients are typed, and responses are parsed into Pydantic models.
- Every response the suite receives is also checked against the service's own OpenAPI document
  (`tests/utils/openapi.py`, jsonschema): an undocumented status code, a missing or undocumented
  field, or a wrong type fails the test that saw it. The Pydantic models say what the tests need;
  this check says whether the API documentation tells the truth.
- The same check tallies which declared responses the suite ever received. At the end of the run
  (also under `pytest-xdist`: workers report, the controller merges) `api-coverage.json` and a
  readable `api-coverage.html` land in the Allure results: every operation of the OpenAPI
  document by every status it declares, hit or not, with the two totals in the report's
  Environment widget and on the landing page (`tests/utils/api_coverage.py`).
- The document itself is pinned in `tests/contract/openapi.json`. Any API change fails
  `tests/contract` until the pinned file is regenerated (`scripts/export_openapi.py`) and committed,
  so the contract change is reviewed in the pull request diff.
- Configuration is loaded with pydantic-settings.
- The API smoke also exists as a Postman collection (`postman/`), for manual QA and developers to
  click through. Newman runs it in the PR, so the collection cannot silently go stale; the admin's
  one-time code is computed in a pre-request script, and credentials come in as `--env-var`.
- A few business scenarios are written in Gherkin (`tests/bdd/features`) so that someone without
  Python can read what the product promises: refunds that add up, safe retries, a declined card, one
  merchant never seeing another's payment, and a refund through the browser. They add no new
  coverage: each sentence is a step that calls the same payment factory, API client and page objects
  as the other layers, and each scenario is bound to a normal test function with its title, tier
  and requirement. In Allure the steps appear as written, under the suite "BDD (Gherkin)".
- Every test outside `tests/unit` traces to a requirement: a GitHub issue labelled
  [`requirement`](https://github.com/pidnebesnyi/portfolio/issues?q=label%3Arequirement) with
  acceptance criteria and the risk it covers. The Allure report links each test to its issue; the
  matrix is in [`docs/test-strategy.md`](docs/test-strategy.md#traceability).
- Markers are enforced: every test has exactly one of `smoke` or `regression`, a known
  requirement, and `--strict-markers` fails on typos. Retries happen only through `@pytest.mark.flaky` with a reason.
- One database test compares the API's whole payment list for a merchant (every page) with the same rows read by SQL. Both sides are normalized explicitly into one plain shape (ids, integer amounts, UTC timestamps, enums, NULL versus empty; one small function per rule in `tests/utils/payment_compare.py`, unit-tested without a database) and compared with a single DeepDiff call. A failure attaches DeepDiff's readable diff to Allure and uses it as the assertion message.
- Browser tests read like the API ones in the report: every page-object action (open, log in, refund, filter) and every `expect(...)` check is an Allure step named after its locator and expectation (`tests/utils/ui_steps.py`), so a UI test no longer shows only the API calls that built its data. Step titles leave typed secrets out.
- In the report a test reads as Arrange / Act / Assert: factories, the requests and page actions a test makes itself, and its checks are steps with those prefixes (`tests/utils/aaa.py`); ten reference tests mark the three phases explicitly.
- Every browser test also watches the HTTP responses its page receives: a broken image, script or
  `fetch` call behind a page that otherwise looks fine fails the test at teardown, with the method,
  URL, status and resource type of each response attached. The few tests that cause an error on
  purpose (a stubbed 500) say so with `@pytest.mark.allow_http_errors(url=..., status=...,
  reason=...)`; the reason is required (`tests/utils/page_health.py`).
  The same listener fingerprints the web font the app serves (Inter, one woff2 under
  `/static/fonts`): a swapped, truncated or wrongly cached font file, or any other font file, fails
  the test unless its SHA-256 equals the pinned one (`tests/utils/font_integrity.py`).
- Computed-style checks are soft (`tests/utils/soft_checks.py`): a mismatch is recorded with its element, property, expected and actual value and a screenshot of the outlined element, the test goes on, and `verify()` fails it once with every mismatch listed. A test that records mismatches and never verifies fails at teardown.
- Each wait for a log line or event is one Allure step, `Wait until ...`, with every polling attempt listed in a "Polling attempts" attachment, so a timeout shows what was seen at each try (`tests/utils/waiting.py`).
- A failed test keeps evidence in Allure: last request and response, last SQL, and for UI tests a
  screenshot, trace and video. Credentials are masked.
- UI tests get their data from the API and verify only what the UI shows.

## Read next

[`docs/test-strategy.md`](docs/test-strategy.md): what is tested at which level and why, the data
and flakiness policies, and what is deliberately not automated.
