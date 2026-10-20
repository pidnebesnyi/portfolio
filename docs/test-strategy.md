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
| 5 | The shape of an API response drifts, and clients break | Silent, costs integrators time |
| 6 | Stored data contradicts itself (refund sums, orphaned rows) | Surfaces later, in reconciliation |
| 7 | The UI cannot complete the main tasks | Visible at once, but cheap to fix |
| 8 | The service gets slow or starts failing under normal load | Matters at scale; here only a regression signal |

## Risk, test level, and why that level

| Risk | Tested at | Why there |
|------|-----------|-----------|
| 1 Double charge, over-refund | API (`tests/api`: idempotency, refunds) and DB (`tests/db`) | The rule lives in the service; one HTTP call proves it in milliseconds. The SQL check confirms the stored sums independently of the API's own answer |
| 2 Wrong state | API: a table of every allowed and forbidden transition (29 cases) | A parametrised table is cheap and readable, and reads like the state machine |
| 2 Provider failure modes | Integration (`tests/integration`) against a provider mock (WireMock) with stubs per card token | Decline, 5xx and timeout cannot be triggered on demand on a real provider. WireMock also records what it received, and the tests read that journal through its admin API, so they assert exactly one charge was attempted |
| 3, 4 Access | API: basic access checks (no token, expired token, wrong signature, another merchant's id) | Cheapest level that sees the response code. Not a security assessment, see the last section |
| 4 Login with 2FA | API for the rules, UI for the form (8 tests, 2 smoke) | The rules are decided by the service; the browser only needs to show the form works |
| 5 Contract | API: every response is parsed into a Pydantic model by the typed clients (`tests/clients`) | A response that no longer matches its model fails the first test that sees it |
| 2 Observability | Log lines of a request found by its request id (`tests/logs`), including a scan for secrets | The id ties a failure to its evidence; a log is also where passwords and tokens leak |
| 2 Event publishing | Consumer on a private RabbitMQ queue (`tests/events`) | Other systems act on these messages; they must be published once, after the commit, with the right data, and never for a rejected request |
| 6 Data consistency | SQL invariants after the API tests created data | Catches states the API never admits to, such as refunds above the amount or one idempotency key mapped to two payments |
| 7 UI | Playwright with page objects, 32 tests; only 6 on every PR | Browser tests are slow and the most fragile, so they check what only a browser can: forms, filters, a refund through the page, how the page behaves when its own fetch call fails, computed fonts and colours. Data is created by the API, never by clicking |
| 8 Performance | Locust, weekly, with a pass/fail rule (p95 500 ms, errors 1 %) | Proves the flow works with 20 concurrent merchants and catches a slowdown. It does not predict production capacity |

## The pyramid as built

| Level | Tests | Runs |
|-------|------:|------|
| Unit (site builder, Allure labels) | 19 | every run |
| API, `tests/api` | 90 | every PR |
| Integration with the WireMock provider stub | 8 | every PR |
| Database invariants | 6 | every PR |
| Log checks, `tests/logs` | 11 | every PR |
| Domain events, `tests/events` | 5 | every PR |
| UI (Playwright) | 32, of which 6 smoke | smoke on every PR, all nightly |
| Load | 1 profile, 4 weighted tasks | weekly |

171 tests in the suite (numbers from the latest local run, the live number is on the landing page).
The shape is a pyramid on purpose: about 53 % of the tests are API checks, about a fifth need a browser.
The application has almost no logic outside the API, so a real unit level does not exist there.
The 19 unit tests cover the plain code around the suite: the landing-page builder and the Allure
suite labels.
22 tests are tagged `smoke`: the critical path, intended to finish in under a minute on a pull request.

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
every password, token, TOTP secret, one-time code and card token it used, for any JWT and for an
`Authorization` value.

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
