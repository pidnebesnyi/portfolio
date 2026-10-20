# Test strategy

The object under test is a small payments service: merchants create a payment, authorize it
through a card provider, capture it, and refund it in parts. The service is deliberately minimal.
The strategy below is about how the risk in such a flow is covered, and where it is not.

## What can go wrong, in order of cost

| # | Risk | Why it ranks here |
|---|------|-------------------|
| 1 | Money moves twice or too much: duplicate charge on retry, refunds adding up to more than the payment | Direct financial loss, hard to reverse |
| 2 | A payment ends in a wrong or hanging state: provider timeout leaves it `authorized`, illegal transitions are accepted | Merchant and customer disagree about what was paid |
| 3 | One merchant sees or changes another merchant's payments | Data leak, trust loss |
| 4 | Login or second factor lets the wrong person in, or locks the right one out | Gate to everything else |
| 5 | The API contract drifts from its documentation, and clients break | Silent, costs integrators time |
| 6 | Stored data contradicts itself (refund sums, orphaned rows) | Surfaces later, in reconciliation |
| 7 | The UI cannot complete the main tasks | Visible at once, but cheap to fix |
| 8 | The service gets slow or starts failing under normal load | Matters at scale; here only a regression signal |

## Risk, test level, and why that level

| Risk | Tested at | Why there |
|------|-----------|-----------|
| 1 Double charge, over-refund | API (`tests/api`: idempotency, refunds, parallel refunds in threads) and DB (`tests/db`) | The rule lives in the service; one HTTP call proves it in milliseconds. Concurrency needs real parallel requests against a real database row lock, so no mocks. The SQL check confirms the stored sums independently of the API's own answer |
| 2 Wrong state | API: a table of every allowed and forbidden transition (29 cases) | A parametrised table is cheap and readable, and reads like the state machine |
| 2 Provider failure modes | Integration (`tests/integration`) against a provider mock that behaves by card token | Decline, 5xx and timeout cannot be triggered on demand on a real provider. The mock also records what it received, so tests assert exactly one charge was attempted |
| 3, 4 Access | API: basic access checks (no token, expired token, wrong signature, another merchant's id) | Cheapest level that sees the response code. Not a security assessment, see the last section |
| 4 Login with 2FA | API for the rules, UI for the form (8 tests, 2 smoke) | The rules are decided by the service; the browser only needs to show the form works |
| 5 Contract | Schemathesis generates requests from `/openapi.json` for all 13 operations | A hand-written test only covers inputs someone thought of |
| 6 Data consistency | SQL invariants after the API tests created data | Catches states the API never admits to, such as refunds above the amount or one idempotency key mapped to two payments |
| 7 UI | Playwright with page objects, 21 tests; only 4 on every PR | Browser tests are slow and the most fragile, so they check what only a browser can: forms, filters, a refund through the page. Data is created by the API, never by clicking |
| 8 Performance | Locust, weekly, with a pass/fail rule (p95 500 ms, errors 1 %) | Proves the flow works with 20 concurrent merchants and catches a slowdown. It does not predict production capacity |

## The pyramid as built

| Level | Tests | Runs |
|-------|------:|------|
| Unit (the landing-page builder) | 12 | every run |
| API, `tests/api` | 95 | every PR |
| Contract, `tests/contract` | 1 test, 13 operations as subtests | every PR |
| Integration with the provider mock | 8 | every PR |
| Database invariants | 7 | every PR |
| UI (Playwright) | 21, of which 4 smoke | smoke on every PR, all nightly |
| Load | 1 profile, 4 weighted tasks | weekly |

144 tests in the suite (numbers from the latest local run, the live number is on the landing page).
The shape is a pyramid on purpose: about two thirds of the tests are API checks, under 15 % need a browser.
The application has almost no logic outside the API, so a real unit level does not exist there.
The 12 unit tests cover the one piece of plain code in the repository (the landing-page builder).
17 tests are tagged `smoke`: the critical path, intended to finish in under a minute on a pull request.

## Data strategy

- All data is created through the admin API, never by SQL inserts or by clicking in the UI. A test
  then uses the same path a real client uses, so a broken endpoint fails loudly instead of
  silently preparing wrong data.
- Every test gets its own merchant with a unique name and a random password, created in a
  fixture. Two tests, and two parallel workers, never touch the same rows. That is why the suite
  runs with `pytest-xdist` (`-n auto`) and in three shards at night without ordering rules.
- Factories remember what they created and delete it at teardown (deleting a merchant cascades to
  payments and refunds), and a database test checks that nothing is left behind. The SQL invariant
  tests scope every query to the test's own merchant, so they stay valid while other tests run.
- Credentials are generated per run (`scripts/make_env.sh`, and in CI with masked values). No secret
  is stored in the repository.
- Provider behaviour is chosen by the card token on each request, not by a global switch, so
  parallel tests cannot disturb each other.

## Flakiness policy

- No global retries. A retry hides the failure it was meant to fix.
- A test is rerun only when it carries `@pytest.mark.flaky(reruns=N, reason="...")`. Collection
  fails when the reason is missing, so every retry is a written decision.
- A test that is unstable and not yet fixed gets `quarantine` and a link to an issue. It is excluded
  from every gate and still visible in the repository. Quarantine is a waiting room with a date,
  not a place to keep tests. There is none at the moment.
- Waits are tied to the thing waited for. A provider hang is capped at the timeout plus one second;
  browser assertions wait for the condition and return as soon as it holds.
- Every test carries exactly one tier marker (`smoke`, `regression` or `quarantine`), and collection
  fails otherwise, so `-m` expressions select what we think they select.

## Seeded bugs: why

A green suite proves little unless it can also go red. Four defects can be switched on in the app,
one per important risk: replayed idempotency key creates a second payment (BUG-1), the over-refund
guard is removed (BUG-2), another merchant's payment is readable (BUG-3), a provider timeout leaves
the payment `authorized` (BUG-4). Each is guarded by tests marked with the bug id (6 tests). A weekly
workflow turns each bug on in turn and requires a marked test to fail, and requires the suite to
be green with no bug on. The result is published on the `bugs` page. If a refactor makes a test
too lenient, this is where it shows.

## Running only the unit tests

The unit tests need no app, database or browser. The shared `conftest.py` still builds the
settings object, so the four credential variables must exist; any value will do:

    JWT_SECRET=x DB_DSN=x ADMIN_PASSWORD=x ADMIN_TOTP_SECRET=x pytest tests/unit

## Deliberately not automated

- **Real provider certification.** The mock proves how this service reacts to declines, errors and
  slowness. It says nothing about a real acquirer's formats, 3-D Secure or settlement files; that
  needs the provider's sandbox and their test plan.
- **Visual and pixel testing.** The UI is a form and a table. Screenshot diffs would cost more
  maintenance than the defects they would find. Screenshots are kept only as failure evidence.
- **Accessibility audit.** Locators use roles and labels, which gives a basic check as a side
  effect. A real audit (screen readers, contrast, keyboard paths) needs a specialist pass.
- **Security testing.** Only basic access checks are automated: missing, expired and forged tokens,
  and cross-merchant access. Penetration testing, dependency and header scanning beyond secret
  scanning in CI are out of scope.
- **Performance at production scale.** The weekly run uses 20 users against one app instance on a
  shared CI runner. It guards against regressions; capacity planning needs production-like
  hardware, data volume and a separate team.
- **Exploratory testing of the UI.** A person with a charter finds the surprising problems no
  script was written for. That is done by hand, and its findings go to the tracker, not to a test.
