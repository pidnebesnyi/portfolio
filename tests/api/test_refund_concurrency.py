"""Two refunds of the same payment fired at the same instant.

The app serialises them with SELECT ... FOR UPDATE. Whatever interleaving the scheduler picks,
the invariants must hold: the refunded total never exceeds the payment amount, and the stored
total, the refund rows and the payment status agree. These checks run against the database
as well as the API, because a response body can look fine while the data is not.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.clients.responses import ApiResponse
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus, Refund
from tests.utils.allure_links import area, requirement
from tests.utils.db import Database

pytestmark = [
    area("Refunds"),
    requirement("PAY-REFUND-CONCURRENCY"),
    pytest.mark.regression,
    pytest.mark.db,
]

AMOUNT = 1000


def _fire_together(calls: list[Callable[[], ApiResponse[Refund]]]) -> list[ApiResponse[Refund]]:
    """Release all calls at once from a barrier so they overlap as much as possible."""
    barrier = threading.Barrier(len(calls))

    def run(call: Callable[[], ApiResponse[Refund]]) -> ApiResponse[Refund]:
        barrier.wait(timeout=10)
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


@pytest.mark.parametrize(
    ("first", "second", "expected_ok", "final_status", "final_total"),
    [
        # Together they would exceed the amount: exactly one wins, the other is a 422.
        pytest.param(600, 600, 1, PaymentStatus.PARTIALLY_REFUNDED, 600, id="overlapping-partials"),
        # Both fit: both must succeed and the payment ends fully refunded.
        pytest.param(500, 500, 2, PaymentStatus.REFUNDED, 1000, id="two-halves"),
        # Two full refunds: the loser sees `refunded` and gets a 409, never a second 201.
        pytest.param(1000, 1000, 1, PaymentStatus.REFUNDED, 1000, id="double-full-refund"),
    ],
)
@allure.title("Parallel refunds never exceed the payment amount: {param_id}")
def test_parallel_refunds_never_exceed_the_payment_amount(
    api: PaymentsApi,
    payment_factory: PaymentFactory,
    db: Database,
    first: int,
    second: int,
    expected_ok: int,
    final_status: PaymentStatus,
    final_total: int,
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=AMOUNT)

    responses = _fire_together(
        [lambda: api.refund(payment.id, first), lambda: api.refund(payment.id, second)]
    )

    ok = [r for r in responses if r.status_code == 201]
    rejected = [r for r in responses if r.status_code != 201]
    assert len(ok) == expected_ok, [(r.status_code, r.raw.text) for r in responses]
    for response in rejected:
        assert response.status_code in (409, 422), response.raw.text
        assert response.error is not None
        assert response.error.code in ("refund_exceeds_amount", "invalid_transition")

    stored = db.fetch_all(
        """
        SELECT p.amount, p.refunded_amount, p.status,
               COALESCE(SUM(r.amount), 0) AS refunds_sum, COUNT(r.id) AS refunds_count
        FROM payments p LEFT JOIN refunds r ON r.payment_id = p.id
        WHERE p.id = %s
        GROUP BY p.id
        """,
        (payment.id,),
    )[0]
    assert stored["refunds_sum"] <= stored["amount"], "refunded more than was paid"
    assert stored["refunds_sum"] == stored["refunded_amount"] == final_total
    assert stored["refunds_count"] == expected_ok
    assert stored["status"] == final_status.value
    assert api.get(payment.id).expect(200).refunded_amount == final_total


@allure.title("Many small parallel refunds stop exactly at the payment amount")
def test_many_small_parallel_refunds_stop_exactly_at_the_amount(
    api: PaymentsApi, payment_factory: PaymentFactory, db: Database
) -> None:
    """Ten refunds of 150 against 1000: exactly six fit (900), the rest must be refused."""
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=AMOUNT)

    responses = _fire_together([lambda: api.refund(payment.id, 150)] * 10)

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201] * 6 + [422] * 4, statuses
    total = db.fetch_value(
        "SELECT COALESCE(SUM(amount), 0) FROM refunds WHERE payment_id = %s", (payment.id,)
    )
    assert total == 900
