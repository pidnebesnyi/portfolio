import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.aaa import act, arrange, check
from tests.utils.allure_links import area, requirement
from tests.utils.db import Database

pytestmark = [area("Refunds"), requirement("PAY-REFUND")]


@pytest.mark.smoke
@allure.title("A refund over the payment amount is rejected")
def test_refund_over_the_payment_amount_is_rejected(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    with arrange("a captured payment of 1000"):
        payment = payment_factory.create(PaymentStatus.CAPTURED, amount=1000)

    with act("refund 1001, one more than the payment"):
        response = api.refund(payment.id, 1001)

    with check("the refusal names the refundable 1000 and the payment is untouched"):
        error = response.expect_error(422, "refund_exceeds_amount")
        assert error.refundable == 1000
        after = api.get(payment.id).expect(200)
        assert (after.status, after.refunded_amount) == (PaymentStatus.CAPTURED, 0)


@pytest.mark.smoke
@allure.title("Partial refunds accumulate until the payment is fully refunded")
def test_partial_refunds_accumulate_until_fully_refunded(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    with arrange("a captured payment of 1000"):
        payment = payment_factory.create(PaymentStatus.CAPTURED, amount=1000)

    with act("refund 300, then 200, then the remaining 500"):
        first = api.refund(payment.id, 300).expect(201)
        second = api.refund(payment.id, 200).expect(201)
        last = api.refund(payment.id, 500).expect(201)

    with check("the payment is partially refunded twice, then fully refunded"):
        assert (first.payment_status, first.refunded_amount) == (
            PaymentStatus.PARTIALLY_REFUNDED,
            300,
        )
        assert (second.payment_status, second.refunded_amount) == (
            PaymentStatus.PARTIALLY_REFUNDED,
            500,
        )
        assert (last.payment_status, last.refunded_amount) == (PaymentStatus.REFUNDED, 1000)
        final = api.get(payment.id).expect(200)
        assert (final.status, final.refunded_amount) == (PaymentStatus.REFUNDED, 1000)


@pytest.mark.regression
@allure.title("A full refund in one call marks the payment refunded")
def test_full_refund_in_one_call_marks_payment_refunded(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=1000)

    refund = api.refund(payment.id, 1000).expect(201)

    assert refund.payment_status is PaymentStatus.REFUNDED
    assert refund.payment_id == payment.id


@pytest.mark.regression
@allure.title("A refund exceeding the remainder is rejected")
def test_refund_exceeding_the_remainder_is_rejected(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    with arrange("a captured payment of 1000 with 700 already refunded"):
        payment = payment_factory.create(PaymentStatus.CAPTURED, amount=1000)
        api.refund(payment.id, 700).expect(201)

    with act("refund 301, one more than the remaining 300"):
        response = api.refund(payment.id, 301)

    with check("the refusal names the refundable 300 and the refunded total stays 700"):
        error = response.expect_error(422, "refund_exceeds_amount")
        assert error.refundable == 300
        assert api.get(payment.id).expect(200).refunded_amount == 700


@pytest.mark.regression
@pytest.mark.parametrize("amount", [0, -1])
@allure.title("A refund amount must be positive: {amount}")
def test_refund_amount_must_be_positive(
    api: PaymentsApi, payment_factory: PaymentFactory, amount: int
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED)

    api.refund(payment.id, amount).expect_error(422, "validation_error")


@pytest.mark.regression
@pytest.mark.db
@allure.title("Refund rows match the payment's refunded total")
def test_refund_rows_match_the_payment_total(
    api: PaymentsApi, payment_factory: PaymentFactory, db: Database
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=900)
    for amount in (100, 250, 50):
        api.refund(payment.id, amount).expect(201)

    row = db.fetch_all(
        """
        SELECT p.refunded_amount, p.status,
               COALESCE(SUM(r.amount), 0) AS refunds_sum, COUNT(r.id) AS n
        FROM payments p LEFT JOIN refunds r ON r.payment_id = p.id
        WHERE p.id = %s
        GROUP BY p.id
        """,
        (payment.id,),
    )[0]
    assert (row["refunds_sum"], row["refunded_amount"], row["n"]) == (400, 400, 3)
    assert row["status"] == "partially_refunded"
