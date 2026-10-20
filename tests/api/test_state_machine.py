"""Payment state machine: every allowed transition, and every forbidden one.

The two tables below are the specification. Adding a status or an action means a new row
(or a deliberate absence) here, and the forbidden table is derived so nothing is forgotten.
"""

from uuid import UUID

import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.clients.responses import ApiResponse
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import Payment, Refund
from tests.models.payments import PaymentStatus as S
from tests.utils.allure_links import area

pytestmark = area("Payment state machine")

AMOUNT = 1000
ACTIONS = ("authorize", "capture", "void", "refund")

# (start status, action) -> resulting status. `refund` is exercised with a partial amount
# unless noted; full refunds are covered in test_refunds.
ALLOWED: dict[tuple[S, str], S] = {
    (S.CREATED, "authorize"): S.AUTHORIZED,
    (S.AUTHORIZED, "capture"): S.CAPTURED,
    (S.AUTHORIZED, "void"): S.VOIDED,
    (S.CAPTURED, "refund"): S.PARTIALLY_REFUNDED,
    (S.PARTIALLY_REFUNDED, "refund"): S.PARTIALLY_REFUNDED,
}
# `failed` is reached by authorizing with the declining card token (see PaymentFactory); how the
# provider's other failure modes end up there is covered in tests/integration.
REACHABLE = (
    S.CREATED,
    S.AUTHORIZED,
    S.CAPTURED,
    S.PARTIALLY_REFUNDED,
    S.REFUNDED,
    S.VOIDED,
    S.FAILED,
)
FORBIDDEN = [(s, a) for s in REACHABLE for a in ACTIONS if (s, a) not in ALLOWED]
# One forbidden pair per kind of mistake is critical-path; the rest is regression.
SMOKE_FORBIDDEN = {(S.CREATED, "capture"), (S.REFUNDED, "refund"), (S.FAILED, "authorize")}


def _perform(
    api: PaymentsApi, payment_id: UUID, action: str
) -> ApiResponse[Payment] | ApiResponse[Refund]:
    """Run one action against the API. A refund uses the smallest amount (1)."""
    match action:
        case "authorize":
            return api.authorize(payment_id)
        case "capture":
            return api.capture(payment_id)
        case "void":
            return api.void(payment_id)
        case "refund":
            return api.refund(payment_id, 1)
        case _:
            raise ValueError(f"unknown action {action!r}")


@pytest.mark.regression
@pytest.mark.parametrize(
    ("start", "action", "expected"),
    [pytest.param(s, a, e, id=f"{s}--{a}-->{e}") for (s, a), e in ALLOWED.items()],
)
@allure.title("Allowed transition: {param_id}")
def test_allowed_transition(
    api: PaymentsApi, payment_factory: PaymentFactory, start: S, action: str, expected: S
) -> None:
    payment = payment_factory.create(start, amount=AMOUNT)

    assert _perform(api, payment.id, action).status_code in (200, 201)

    after = api.get(payment.id).expect(200)
    assert after.status is expected


@pytest.mark.parametrize(
    ("start", "action"),
    [
        pytest.param(
            s,
            a,
            id=f"{s}--{a}",
            marks=pytest.mark.smoke if (s, a) in SMOKE_FORBIDDEN else pytest.mark.regression,
        )
        for s, a in FORBIDDEN
    ],
)
@allure.title("A forbidden transition is rejected and changes nothing: {param_id}")
def test_forbidden_transition_is_rejected_and_changes_nothing(
    api: PaymentsApi, payment_factory: PaymentFactory, start: S, action: str
) -> None:
    payment = payment_factory.create(start, amount=AMOUNT)
    before = api.get(payment.id).expect(200)

    error = _perform(api, payment.id, action).expect_error(409, "invalid_transition")
    assert error.from_status == start.value
    assert error.action == action
    assert api.get(payment.id).expect(200) == before, "a rejected transition must not mutate"


@pytest.mark.regression
@allure.title("The forbidden table covers every status and action pair")
def test_forbidden_table_covers_every_pair() -> None:
    """Guards the guard: if ALLOWED or REACHABLE change, the sizes below must be revisited."""
    assert len(ALLOWED) + len(FORBIDDEN) == len(REACHABLE) * len(ACTIONS)
    assert len(FORBIDDEN) == 23
