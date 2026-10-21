"""Requests that arrive at the same moment.

Every rule below is enforced with a row lock or a unique constraint in the service. One request at
a time can never show a broken lock, so these tests send the requests together
(tests/utils/parallel.py) and check the outcome adds up whichever request wins.
"""

from collections import Counter
from uuid import uuid4

import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.aaa import act, arrange, check
from tests.utils.allure_links import area, requirement
from tests.utils.db import Database
from tests.utils.parallel import run_together

pytestmark = area("Concurrency")


@pytest.mark.regression
@requirement("PAY-REFUND")
@allure.title("Parallel refunds never exceed the payment amount")
def test_parallel_refunds_never_exceed_the_payment_amount(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    with arrange("a captured payment of 1000"):
        payment = payment_factory.create(PaymentStatus.CAPTURED, amount=1000)

    with act("send six refunds of 300 at the same moment"):
        answers = run_together([lambda: api.refund(payment.id, 300) for _ in range(6)])

    with check("exactly three are accepted, three refused, and 900 is refunded"):
        assert Counter(a.status_code for a in answers) == {201: 3, 422: 3}
        for rejected in (a for a in answers if a.status_code == 422):
            assert rejected.error is not None
            assert rejected.error.code == "refund_exceeds_amount"
        final = api.get(payment.id).expect(200)
        assert (final.status, final.refunded_amount) == (PaymentStatus.PARTIALLY_REFUNDED, 900)


@pytest.mark.regression
@requirement("PAY-REFUND")
@allure.title("Parallel refunds that add up to the amount leave the payment refunded")
def test_parallel_refunds_that_fit_exactly_leave_the_payment_refunded(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=1000)

    answers = run_together([lambda: api.refund(payment.id, 250) for _ in range(4)])

    assert [a.status_code for a in answers] == [201] * 4
    final = api.get(payment.id).expect(200)
    assert (final.status, final.refunded_amount) == (PaymentStatus.REFUNDED, 1000)


@pytest.mark.regression
@pytest.mark.db
@requirement("PAY-REFUND")
@allure.title("Parallel refunds leave one refund row per accepted request")
def test_parallel_refunds_leave_one_row_per_accepted_request(
    api: PaymentsApi, payment_factory: PaymentFactory, db: Database
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=600)

    answers = run_together([lambda: api.refund(payment.id, 200) for _ in range(5)])

    accepted = sum(a.status_code == 201 for a in answers)
    rows = db.fetch_all(
        "SELECT count(*) AS n, COALESCE(sum(amount), 0) AS total "
        "FROM refunds WHERE payment_id = %s",
        (payment.id,),
    )[0]
    assert (accepted, rows["n"], rows["total"]) == (3, 3, 600)


@pytest.mark.regression
@requirement("PAY-IDEMP")
@allure.title("Parallel requests with one idempotency key create one payment")
def test_parallel_requests_with_one_key_create_one_payment(api: PaymentsApi) -> None:
    key = str(uuid4())

    answers = run_together([lambda: api.create(amount=777, idempotency_key=key) for _ in range(6)])

    assert Counter(a.status_code for a in answers) == {201: 1, 200: 5}
    assert len({a.expect(a.status_code).id for a in answers}) == 1
    assert api.list_payments().expect(200).total == 1


@pytest.mark.regression
@requirement("PAY-IDEMP")
@allure.title("Parallel requests with one key but different bodies: one wins, the rest conflict")
def test_parallel_requests_with_one_key_and_different_bodies(api: PaymentsApi) -> None:
    key = str(uuid4())

    answers = run_together(
        [
            lambda amount=amount: api.create(amount=amount, idempotency_key=key)
            for amount in (1, 2, 3)
        ]
    )

    assert Counter(a.status_code for a in answers) == {201: 1, 409: 2}
    assert api.list_payments().expect(200).total == 1


@pytest.mark.regression
@requirement("PAY-STATE")
@allure.title("Capture and void racing on an authorized payment: exactly one wins")
def test_capture_and_void_racing_exactly_one_wins(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.AUTHORIZED)

    capture, void = run_together([lambda: api.capture(payment.id), lambda: api.void(payment.id)])

    assert sorted([capture.status_code, void.status_code]) == [200, 409]
    winner = PaymentStatus.CAPTURED if capture.status_code == 200 else PaymentStatus.VOIDED
    assert api.get(payment.id).expect(200).status is winner
