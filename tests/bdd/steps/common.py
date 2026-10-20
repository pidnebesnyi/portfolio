"""Steps shared by several features, and the `scene` that carries results between steps.

Steps only call what the rest of the suite already has: payment_factory, the typed API client,
the merchant fixtures. Nothing here talks HTTP or SQL on its own.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from pytest_bdd import given, parsers, then

from tests.clients.payments_api import PaymentsApi
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import Payment, PaymentStatus


def minor_units(amount: str) -> int:
    """'10.00' -> 1000: Gherkin talks in money, the API in minor units."""
    return int(Decimal(amount) * 100)


@dataclass
class Scene:
    """What earlier steps produced for later ones; one per scenario."""

    payment: Payment | None = None
    response: Any = None  # the last ApiResponse a When step got
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def payment_id(self) -> UUID:
        assert self.payment is not None, "no payment yet: a Given step must create one"
        return self.payment.id


@pytest.fixture
def scene() -> Scene:
    return Scene()


@given(parsers.parse("a captured payment of {amount} UAH"))
def a_captured_payment(scene: Scene, payment_factory: PaymentFactory, amount: str) -> None:
    scene.payment = payment_factory.create(PaymentStatus.CAPTURED, amount=minor_units(amount))


@given("a payment that belongs to the merchant")
def a_payment_of_the_merchant(scene: Scene, payment_factory: PaymentFactory) -> None:
    scene.payment = payment_factory.create()


@then(parsers.parse("the payment is {status} with {amount} UAH refunded"))
def the_payment_is_refunded_by(scene: Scene, api: PaymentsApi, status: str, amount: str) -> None:
    stored = api.get(scene.payment_id).expect(200)
    assert (stored.status.value, stored.refunded_amount) == (status, minor_units(amount)), (
        f"expected {status} with {amount} UAH refunded, "
        f"found {stored.status.value} with {stored.refunded_amount / 100:.2f} UAH"
    )
