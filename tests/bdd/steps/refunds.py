from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.common import Scene, minor_units
from tests.clients.payments_api import PaymentsApi


@given(parsers.parse("the merchant has already refunded {amount} UAH"))
def already_refunded(scene: Scene, api: PaymentsApi, amount: str) -> None:
    if minor_units(amount):
        api.refund(scene.payment_id, minor_units(amount)).expect(201)


@when(parsers.parse("the merchant refunds {amount} UAH"))
def the_merchant_refunds(scene: Scene, api: PaymentsApi, amount: str) -> None:
    scene.response = api.refund(scene.payment_id, minor_units(amount))


@then(parsers.parse("the refund is {outcome}"))
def the_refund_is(scene: Scene, outcome: str) -> None:
    if outcome == "accepted":
        response = scene.response
        assert response.status_code == 201, (
            f"the refund should have been accepted, but the service answered "
            f"{response.status_code}: {response.raw.text}"
        )
    else:
        assert outcome == "rejected", f"unknown outcome {outcome!r}: use accepted or rejected"
        scene.response.expect_error(422, "refund_exceeds_amount")
