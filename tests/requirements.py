"""Requirements the suite traces to.

Each one is a GitHub issue labelled `requirement` with its acceptance criteria, the risk it covers
(docs/test-strategy.md) and the tests that check it:
https://github.com/pidnebesnyi/portfolio/issues?q=label%3Arequirement

A test names its requirement with `requirement("PAY-REFUND")` (tests/utils/allure_links.py); the
Allure report then links the test to the issue. Collection fails for an id missing here and for
a test outside tests/unit that names none, so the trace cannot silently rot.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Requirement:
    issue: int
    title: str


REQUIREMENTS: dict[str, Requirement] = {
    "PAY-CREATE": Requirement(32, "A merchant creates a payment; invalid input is rejected"),
    "PAY-LIST": Requirement(33, "A merchant lists own payments with filters and pagination"),
    "PAY-STATE": Requirement(
        34, "A payment follows its state machine; forbidden transitions change nothing"
    ),
    "PAY-PROVIDER": Requirement(35, "Provider decline, error and timeout end in a defined state"),
    "PAY-IDEMP": Requirement(36, "Payment creation is idempotent per merchant and key"),
    "PAY-REFUND": Requirement(37, "Partial refunds never exceed the payment amount"),
    "PAY-ACCESS": Requirement(
        38, "A merchant reaches only own payments; roles and tokens are enforced"
    ),
    "PAY-REFRESH": Requirement(
        39, "The payment page refreshes its status and copes with backend failures"
    ),
    "AUTH-LOGIN": Requirement(40, "Login with a password, and a second factor for admins"),
    "MERCH-CREATE": Requirement(41, "An admin creates and lists merchants"),
    "MERCH-DELETE": Requirement(42, "Deleting a merchant removes their data and revokes access"),
    "EVT-PUBLISH": Requirement(
        43, "Payment changes are published as events, once, after the commit"
    ),
    "OBS-LOG": Requirement(44, "Every request is traceable in a structured log without secrets"),
    "OBS-HEALTH": Requirement(45, "The health endpoint reports whether the database is reachable"),
    "API-CONTRACT": Requirement(
        46, "The API matches its published OpenAPI document; changes are reviewed"
    ),
    "UI-STYLE": Requirement(47, "The UI uses the defined fonts and colours"),
}
