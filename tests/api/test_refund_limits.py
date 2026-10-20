"""Refund amounts at their edges, and what a refund body may not contain."""

from typing import Any
from uuid import uuid4

import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.allure_links import area, requirement

pytestmark = [area("Refunds"), requirement("PAY-REFUND")]


@pytest.mark.regression
@allure.title("The smallest payment can be refunded in full")
def test_smallest_payment_can_be_refunded_in_full(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=1)

    refund = api.refund(payment.id, 1).expect(201)

    assert (refund.payment_status, refund.refunded_amount) == (PaymentStatus.REFUNDED, 1)


@pytest.mark.regression
@allure.title("Many small refunds add up to exactly the payment amount")
def test_many_small_refunds_add_up_exactly(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=10)

    statuses = [api.refund(payment.id, 1).expect(201).payment_status for _ in range(10)]

    assert statuses[:-1] == [PaymentStatus.PARTIALLY_REFUNDED] * 9
    assert statuses[-1] is PaymentStatus.REFUNDED
    api.refund(payment.id, 1).expect_error(409, "invalid_transition")


@pytest.mark.regression
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"amount": 1.5}, id="fractional"),
        pytest.param({"amount": "100"}, id="text"),
        pytest.param({"amount": None}, id="null"),
        pytest.param({}, id="missing"),
        pytest.param({"amount": 100_000_001}, id="above-the-ceiling"),
        pytest.param({"amount": True}, id="boolean"),
    ],
)
@allure.title("A refund body that is not a whole positive amount is rejected: {param_id}")
def test_malformed_refund_body_is_rejected(
    api: PaymentsApi, payment_factory: PaymentFactory, body: dict[str, Any]
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED)

    api.refund_raw(payment.id, body).expect_error(422, "validation_error")

    assert api.get(payment.id).expect(200).refunded_amount == 0


@pytest.mark.regression
@allure.title("Refunding a payment nobody owns is not found")
def test_refund_of_an_unknown_payment_is_not_found(api: PaymentsApi) -> None:
    api.refund(uuid4(), 100).expect_error(404, "payment_not_found")
