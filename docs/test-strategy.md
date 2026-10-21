# Test strategy

The system under test is a small demo service whose example domain is payments: merchants create a
payment, authorize it through an external provider, capture it, and refund it in parts. The service
is deliberately minimal. The strategy below is about how its risk is covered, and where it is not;
the same layers (API, SQL, browser, queue, logs, stubbed dependency, load) apply to any service
built from an API, a database, a UI, a message broker and an external dependency.

## What can go wrong, in order of cost

| # | Risk | Why it ranks here |
|---|------|-------------------|
| 1 | Money moves twice or too much: duplicate charge on retry, refunds adding up to more than the payment | Direct financial loss, hard to reverse |
| 2 | A payment ends in a wrong or hanging state: provider timeout leaves it `authorized`, illegal transitions are accepted | Merchant and customer disagree about what was paid |
| 3 | One merchant sees or changes another merchant's payments | Data leak, trust loss |
| 4 | Login or second factor lets the wrong person in, or locks the right one out | Gate to everything else |
| 5 | The shape of an API response drifts, and clients break | Silent, costs integrators time |
| 6 | Stored data contradicts itself (refund sums, orphaned rows) | Surfaces later, in reconciliation |
| 7 | The UI cannot complete the main tasks | Visible at once, but cheap to fix |
| 8 | The service gets slow or starts failing under normal load | Matters at scale; here only a regression signal |

## Risk, test level, and why that level

| Risk | Tested at | Why there |
|------|-----------|-----------|
| 1 Double charge, over-refund | API (`tests/api`: idempotency, refunds) and DB (`tests/db`) | The rule lives in the service; one HTTP call proves it in milliseconds. The SQL check confirms the stored sums independently of the API's own answer |
| 2 Wrong state | API: a table of every status and action pair, allowed or forbidden (28 cases, plus a check that the table covers them all) | A parametrised table is cheap and readable, and reads like the state machine |
| 2 Provider failure modes | Integration (`tests/integration`) against a provider mock (WireMock) with stubs per card token | Decline, 5xx and timeout cannot be triggered on demand on a real provider. WireMock also records what it received, and the tests read that journal through its admin API, so they assert exactly one charge was attempted |
| 3, 4 Access | API: basic access checks (no token, expired token, wrong signature, another merchant's id) | Cheapest level that sees the response code. Not a security assessment, see the last section |
| 4 Login with 2FA | API for the rules, UI for the form (8 tests, 2 smoke) | The rules are decided by the service; the browser only needs to show the form works |
| 5 Contract | API: every response is parsed into a Pydantic model by the typed clients (`tests/clients`) and checked against the service's own OpenAPI document; the document is pinned in `tests/contract/openapi.json` | A response that no longer matches its model or its documentation fails the first test that sees it. Pinning catches the case where code and documentation change together: integrators break although every response matches, so the change must appear in the pull request diff |
| 2 Observability | Log lines of a request found by its request id (`tests/logs`), including a scan for secrets | The id ties a failure to its evidence; a log is also where passwords and tokens leak |
| 2 Event publishing | Consumer on a private RabbitMQ queue (`tests/events`) | Other systems act on these messages; they must be published once, after the commit, with the right data, and never for a rejected request |
| 6 Data consistency | SQL invariants after the API tests created data | Catches states the API never admits to, such as refunds above the amount or one idempotency key mapped to two payments. One test also compares the API's full payment list with the SQL rows field by field in a single DeepDiff call, after both sides are normalized to one shape (amounts, timestamps, ids, NULL versus empty) |
| 7 UI | Playwright with page objects, 32 tests; only 6 on every PR | Browser tests are slow and the most fragile, so they check what only a browser can: forms, filters, a refund through the page, how the page behaves when its own fetch call fails, computed fonts and colours. Data is created by the API, never by clicking |
| 8 Performance | Locust, weekly, with a pass/fail rule (p95 500 ms, errors 1 %) | Proves the flow works with 20 concurrent merchants and catches a slowdown. It does not predict production capacity |

## The pyramid as built

| Level | Tests | Runs |
|-------|------:|------|
| Unit (site builder, Allure labels and UI step names, Arrange/Act/Assert labels, OpenAPI checker, requirement trace) | 49 | every run |
| API, `tests/api` | 160 | every PR |
| OpenAPI contract, `tests/contract` | 1 | every PR |
| Integration with the WireMock provider stub | 9 | every PR |
| Database invariants | 6 | every PR |
| Log checks, `tests/logs` | 11 | every PR |
| Gherkin scenarios, `tests/bdd` | 9 (5 are rows of one outline), of which 1 in the browser | API scenarios every PR, browser scenario nightly |
| Domain events, `tests/events` | 5 | every PR |
| UI (Playwright) | 69, of which 6 smoke | smoke on every PR, all nightly |
| Postman collection (Newman), `postman/` | 20 requests, 59 assertions | every PR |
| Load | 1 profile, 4 weighted tasks | weekly |

319 tests in the suite (numbers from the latest local run, the live number is on the landing page).
The shape is a pyramid on purpose: about half of the tests are API checks, about a fifth need a browser.
The application has almost no logic outside the API, so a real unit level does not exist there.
The 49 unit tests cover the plain code around the suite: the landing-page builder, the Allure
suite labels, the requirement trace and the OpenAPI checker, which is made to fail on purpose for each kind of violation.
22 tests are tagged `smoke`: the critical path, intended to finish in under a minute on a pull request.

The Gherkin scenarios in `tests/bdd` are a reading layer, not new coverage. They restate five
behaviours already checked in `tests/api`, `tests/integration` and `tests/ui` (partial refunds that
never exceed the payment, a repeated request returning the same payment, a declined card ending as
failed, one merchant not seeing another's payment, a refund through the browser) in business words,
for readers who do not write Python. The steps call the same factories, clients and page objects, so
there is no second framework to maintain. Each scenario is bound to a test function that carries
its Allure title, tier and requirement, which keeps the collection checks below in force.

Depth beyond the happy path, by design:

- **Limits.** Each input has a test at the largest value that passes and the first that fails
  (amount ceiling, text lengths, idempotency key length, page sizes, merchant name and password).
- **Races.** The service relies on a row lock (`SELECT ... FOR UPDATE`) and a unique constraint.
  One request at a time cannot show a broken lock, so `tests/api/test_concurrency.py` and
  `tests/integration/test_concurrent_authorize.py` send requests together
  (`tests/utils/parallel.py`): parallel refunds never exceed the amount, one idempotency key makes
  one payment, capture and void race to exactly one winner, and the provider is charged once.
  Removing the lock from the service makes five of these fail; that check was done by hand.
- **Tokens.** Unsigned, expiry-less, wrongly typed and orphaned tokens are refused.
- **Browser access and navigation.** Titles and headings, links, redirects, the back button with
  filters, an admin on merchant pages, another merchant's payment, forged or stale sessions.

How a test reads in the Allure report:

- **Arrange / Act / Assert, automatically** (`tests/utils/aaa.py`). The payment and merchant
  factories are `Arrange: ...` steps with their requests inside; a request or page-object action
  the test makes itself is `Act: ...`; `expect(...)`, `expect_error(...)` and every browser
  `expect(...)` are `Assert: ...`. Fixture setup and teardown stay unlabelled, and the Gherkin
  scenarios keep their own Given / When / Then.
- **Explicit phases where it helps.** A plain `assert` cannot be a step, so a test that should show
  its structure wraps its code in `arrange(...)`, `act(...)` and `check(...)`. Used in ten
  tests (refunds, idempotency, state machine, races, the browser refund) as the reference
  shape; the rest rely on the automatic labels. Phases never nest, so nothing is labelled twice.

## Traceability

Requirements live as GitHub issues labelled
[`requirement`](https://github.com/pidnebesnyi/portfolio/issues?q=label%3Arequirement), each with
acceptance criteria, the risks above it covers and the tests that check it. Tests name their
requirement with `requirement("PAY-REFUND")`; `tests/requirements.py` maps each id to its issue.
The chain is checked, not trusted:

- collection fails for an unknown id, and for a test outside `tests/unit` that names none;
- a unit test fails when a requirement is named by no test;
- in the Allure report every test links to its issue, and the Behaviors tab groups tests by
  area and requirement.

| Requirement | What | Risk | Tests |
|---|---|---|---|
| [PAY-CREATE](https://github.com/pidnebesnyi/portfolio/issues/32) | A merchant creates a payment; invalid input is rejected | 7 | [`api/test_payments.py`](../tests/api/test_payments.py), [`ui/test_create_payment.py`](../tests/ui/test_create_payment.py) |
| [PAY-LIST](https://github.com/pidnebesnyi/portfolio/issues/33) | A merchant lists own payments with filters and pagination | 3, 6, 7 | [`api/test_payments.py`](../tests/api/test_payments.py), [`ui/test_filters.py`](../tests/ui/test_filters.py), [`db/test_totals_and_cleanup.py`](../tests/db/test_totals_and_cleanup.py) |
| [PAY-STATE](https://github.com/pidnebesnyi/portfolio/issues/34) | A payment follows its state machine; forbidden transitions change nothing | 2 | [`api/test_state_machine.py`](../tests/api/test_state_machine.py) |
| [PAY-PROVIDER](https://github.com/pidnebesnyi/portfolio/issues/35) | Provider decline, error and timeout end in a defined state | 1, 2 | [`integration/test_provider.py`](../tests/integration/test_provider.py), [`bdd/test_provider.py`](../tests/bdd/test_provider.py) |
| [PAY-IDEMP](https://github.com/pidnebesnyi/portfolio/issues/36) | Payment creation is idempotent per merchant and key | 1, 6 | [`api/test_idempotency.py`](../tests/api/test_idempotency.py), [`db/test_idempotency_keys.py`](../tests/db/test_idempotency_keys.py), [`bdd/test_idempotency.py`](../tests/bdd/test_idempotency.py) |
| [PAY-REFUND](https://github.com/pidnebesnyi/portfolio/issues/37) | Partial refunds never exceed the payment amount | 1, 6, 7 | [`api/test_refunds.py`](../tests/api/test_refunds.py), [`db/test_refund_consistency.py`](../tests/db/test_refund_consistency.py), [`ui/test_refund.py`](../tests/ui/test_refund.py), [`bdd/test_refunds.py`](../tests/bdd/test_refunds.py), [`bdd/test_ui_refund.py`](../tests/bdd/test_ui_refund.py) |
| [PAY-ACCESS](https://github.com/pidnebesnyi/portfolio/issues/38) | A merchant reaches only own payments; roles and tokens are enforced | 3 | [`api/test_access.py`](../tests/api/test_access.py), [`bdd/test_access.py`](../tests/bdd/test_access.py) |
| [PAY-REFRESH](https://github.com/pidnebesnyi/portfolio/issues/39) | The payment page refreshes its status and copes with backend failures | 7 | [`ui/test_status_refresh.py`](../tests/ui/test_status_refresh.py) |
| [AUTH-LOGIN](https://github.com/pidnebesnyi/portfolio/issues/40) | Login with a password, and a second factor for admins | 4, 7 | [`api/test_health_and_auth.py`](../tests/api/test_health_and_auth.py), [`ui/test_login.py`](../tests/ui/test_login.py) |
| [MERCH-CREATE](https://github.com/pidnebesnyi/portfolio/issues/41) | An admin creates and lists merchants | 4 | [`api/test_merchants.py`](../tests/api/test_merchants.py) |
| [MERCH-DELETE](https://github.com/pidnebesnyi/portfolio/issues/42) | Deleting a merchant removes their data and revokes access | 4, 6 | [`api/test_merchants.py`](../tests/api/test_merchants.py), [`db/test_totals_and_cleanup.py`](../tests/db/test_totals_and_cleanup.py) |
| [EVT-PUBLISH](https://github.com/pidnebesnyi/portfolio/issues/43) | Payment changes are published as events, once, after the commit | 2 | [`events/test_payment_events.py`](../tests/events/test_payment_events.py) |
| [OBS-LOG](https://github.com/pidnebesnyi/portfolio/issues/44) | Every request is traceable in a structured log without secrets | 2 | [`logs/test_request_log.py`](../tests/logs/test_request_log.py) |
| [OBS-HEALTH](https://github.com/pidnebesnyi/portfolio/issues/45) | The health endpoint reports whether the database is reachable | 8 | [`api/test_health_and_auth.py`](../tests/api/test_health_and_auth.py) |
| [API-CONTRACT](https://github.com/pidnebesnyi/portfolio/issues/46) | The API matches its published OpenAPI document; changes are reviewed | 5 | [`contract/test_pinned_contract.py`](../tests/contract/test_pinned_contract.py), [`utils/openapi.py`](../tests/utils/openapi.py) |
| [UI-STYLE](https://github.com/pidnebesnyi/portfolio/issues/47) | The UI uses the defined fonts and colours | 7 | [`ui/test_styles.py`](../tests/ui/test_styles.py) |

Risk 8 (slow under load) is covered by the Locust profile in `load/`, outside pytest; OBS-HEALTH
is only its smallest part.

The Postman collection in `postman/` names its folders with the same ids (OBS-HEALTH, AUTH-LOGIN,
MERCH-CREATE, PAY-CREATE, PAY-IDEMP, PAY-STATE, PAY-REFUND, PAY-LIST, PAY-ACCESS, MERCH-DELETE).
It repeats the main path the pytest suite already covers, as a hand-over for people who work in
Postman, so it adds no requirement of its own and the guards above do not apply to it.

## Browser techniques

Two techniques that are about the browser, not about payments. The payment detail page is the
subject only because it has one small `fetch` call to exercise.

### Network interception (`tests/ui/test_status_refresh.py`)

- **What.** The detail page has a "Refresh status" button that calls `GET /ui/payments/{id}/status`
  with `fetch` and rewrites the status, or shows an error. The tests replace that one endpoint with
  `page.route`: a made-up JSON answer (the page renders what the server says, even a state the
  payment is not in), a 500, a dropped connection (`route.abort`), and an answer that is held until
  the test releases it (loading state first, then the value). One test removes the stub with
  `page.unroute` and checks the error clears on a retry that reaches the real server, and one
  uses no stub at all and changes the status through the API behind the page's back.
- **Why.** A failing or slow backend cannot be summoned on demand, and a page that only works when
  everything answers is a page nobody tested. Waiting is `expect()` on the page; the held request
  is released by the test, so there is no sleep and no timing luck. Routes are removed in a
  fixture at teardown.
- **Does not cover.** The server side of the endpoint beyond what the real-answer test touches,
  real network conditions (latency, packet loss), and any browser other than chromium.

### Computed fonts and colours (`tests/ui/test_styles.py`)

- **What.** `getComputedStyle` of key elements (body, heading, labels, table cells, header rule,
  success and error messages) compared with the values the app's stylesheet defines. The
  expected values live in one file, `tests/ui/design_tokens.py`, with the CSS they come from next
  to each.
- **Why.** The browser's final answer is what a user sees: a typo in a selector, an overridden
  rule or a changed colour fails a test although the CSS file looks fine. The comparison is on a
  whole dict, so one failure lists every property that differs.
- **Does not cover.** Layout, spacing between elements, and anything pictorial: there are no
  screenshot comparisons, which this small UI does not justify. The app has no custom button or badge styling, so there is nothing to compare for them.

## Data strategy

- All data is created through the admin API, never by SQL inserts or by clicking in the UI. A test
  then uses the same path a real client uses, so a broken endpoint fails loudly instead of
  silently preparing wrong data.
- Every test gets its own merchant with a unique name and a random password, created in a
  fixture. Two tests, and two parallel workers, never touch the same rows. That is why the suite
  runs with `pytest-xdist` (`-n auto`) without ordering rules.
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
- Waits are tied to the thing waited for. A provider hang is capped at the timeout plus one second;
  browser assertions wait for the condition and return as soon as it holds.
- Every test carries exactly one tier marker (`smoke` or `regression`), and collection
  fails otherwise, so `-m` expressions select what we think they select.

## Log checks: structured logs as evidence

**What.** The app writes one JSON line per request (request id, method, path, status, duration,
merchant id when authenticated) and one line per domain event inside it (payment created, status
changed, transition rejected, refund accepted or rejected). A caller may send `X-Request-ID`; a
plain token is kept, anything else is replaced. The id is returned in the response header and sits
on every line of that request. The app appends the lines to a file (`LOG_FILE`); compose shares it
with the tests container as a read-only volume (`APP_LOG_FILE`). `tests/logs` finds a request's
lines by the id from its response and checks them: the same id throughout, a refund's events in
order, a rejected transition and a rejected refund logged as rejections, an unauthenticated call
without a merchant, a hostile `X-Request-ID` not reaching the log. One test runs a login with
password and second factor, a payment with a card token and a refund, then scans the whole log for
every password, token, TOTP secret and card token it used, for any JWT and for an `Authorization`
value. The six-digit one-time code is too short to search for in free text, so it is compared with
every field value of that test's own lines.

**Why.** When a test fails in CI, the log lines of that request say what the service thought it
did. The failing test attaches them to Allure next to the last request, response and SQL. Whether
secrets stay out of the log is a risk no functional test sees.

**Not covered.** Log shipping and retention, a search backend, log levels and the format of
uvicorn's own access log (it is not written to the file). The secret scan proves the values this
run used are absent; it cannot prove no secret is ever logged. The access line is written after
the response, so tests poll with a deadline (`tests/utils/waiting.py`) rather than sleep.

## Domain events on RabbitMQ

**What.** After the database commit the app publishes a JSON message to the durable topic exchange
`payments.events`; the routing key is the event type (`payment.created`, `authorized`, `captured`,
`voided`, `failed`, `refunded`). The body has an event id, payment id, merchant id, amount,
refund amount, refunded total, status, time and the request id, so an event can be matched with
the HTTP response and the log. Each test in `tests/events` binds its own exclusive, auto-delete
queue before acting (parallel workers never take each other's messages), waits for a message with
a deadline that blocks on the connection (no sleeps), validates it with a Pydantic model and
attaches the received messages to Allure. Absence ("a rejected request publishes nothing") is
proven by performing the next real action and waiting for its event: the queue keeps publish
order, so nothing earlier can be hiding.

**Broker down.** The broker is not on the correctness path: the payment request succeeds, the
failure is logged as `event.publish_failed` (exception class only, never the connection URL) and
the event is lost. That is at-most-once delivery by choice; a production design would write the
event to an outbox table in the same transaction. This was checked by hand with the broker
stopped (201 in 10 ms, failure logged); it is not an automated test, because that needs a broker
the test can stop without disturbing other workers.

**Not covered.** Redelivery, dead-letter queues, ordering across publishers, consumer
acknowledgements and retries, clustering, throughput, durability across a broker restart. The app does not use publisher
confirms: with them a publish that races another test's queue being deleted is nacked although
every other queue got the message, which produced false `publish_failed` lines (and duplicate
messages once retried). Delivery is at-most-once anyway, so the simpler publish was kept.

## Running only the unit tests

The unit tests need no app, database or browser. The shared `conftest.py` still builds the
settings object, so the four credential variables must exist; any value will do:

    JWT_SECRET=x DB_DSN=x ADMIN_PASSWORD=x ADMIN_TOTP_SECRET=x pytest tests/unit

## Deliberately not automated

- **Real provider certification.** The mock proves how this service reacts to declines, errors and
  slowness. It says nothing about a real acquirer's formats, 3-D Secure or settlement files; that
  needs the provider's sandbox and their test plan.
- **Pixel-level visual testing.** The UI is a form and a table. Screenshot diffs would cost more
  maintenance than the defects they would find. Fonts and colours are checked as computed values
  (see above); screenshots are kept only as failure evidence.
- **Accessibility audit.** Locators use roles and labels, which gives a basic check as a side
  effect. A real audit (screen readers, contrast, keyboard paths) needs a specialist pass.
- **Security testing.** Only basic access checks are automated: missing, expired and forged tokens,
  and cross-merchant access. Penetration testing and header or DAST scanning are out of scope.
- **Performance at production scale.** The weekly run uses 20 users against one app instance on a
  shared CI runner. It guards against regressions; capacity planning needs production-like
  hardware, data volume and a separate team.
- **Exploratory testing of the UI.** A person with a charter finds the surprising problems no
  script was written for. That is done by hand, and its findings go to the tracker, not to a test.
