from uuid import uuid4

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.common import Scene, minor_units
from tests.clients.payments_api import PaymentsApi

REPLAY_HEADER = "Idempotent-Replayed"


@given(parsers.parse("the merchant has sent a request for a {amount} UAH payment"))
def the_first_request(scene: Scene, api: PaymentsApi, amount: str) -> None:
    scene.extras["key"] = str(uuid4())
    scene.extras["amount"] = minor_units(amount)
    scene.payment = api.create(
        amount=scene.extras["amount"], idempotency_key=scene.extras["key"]
    ).expect(201)


@when("the merchant sends exactly the same request again")
def the_same_request_again(scene: Scene, api: PaymentsApi) -> None:
    scene.response = api.create(amount=scene.extras["amount"], idempotency_key=scene.extras["key"])


@then("the merchant gets the same payment back, marked as a repeat")
def the_same_payment_comes_back(scene: Scene) -> None:
    again = scene.response.expect(200)
    assert again == scene.payment, "the repeat returned a different payment"
    assert scene.response.headers[REPLAY_HEADER] == "true", "the repeat is not marked as a repeat"


@then("the merchant has only one payment")
def only_one_payment(api: PaymentsApi) -> None:
    total = api.list_payments().expect(200).total
    assert total == 1, f"expected 1 payment, the merchant has {total}"
