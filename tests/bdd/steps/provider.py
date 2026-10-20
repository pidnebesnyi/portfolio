from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.common import Scene, minor_units
from tests.clients.payments_api import PaymentsApi
from tests.clients.provider_stub import ProviderStub
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus


@given(parsers.parse("a {amount} {currency} payment with a card the provider will decline"))
def a_payment_with_a_declined_card(
    scene: Scene, payment_factory: PaymentFactory, amount: str, currency: str
) -> None:
    scene.payment = payment_factory.create(
        amount=minor_units(amount), currency=currency, card_token="tok_decline"
    )


@when("the merchant authorizes the payment")
def the_merchant_authorizes(scene: Scene, api: PaymentsApi) -> None:
    scene.payment = api.authorize(scene.payment_id).expect(200)


@then("the payment has failed because it was declined")
def the_payment_failed_declined(scene: Scene, api: PaymentsApi) -> None:
    assert (scene.payment.status, scene.payment.failure_reason) == (
        PaymentStatus.FAILED,
        "declined",
    )
    stored = api.get(scene.payment_id).expect(200)
    assert (stored.status, stored.failure_reason) == (PaymentStatus.FAILED, "declined"), (
        f"the stored payment is {stored.status.value}, reason {stored.failure_reason!r}"
    )


@then("the provider was asked to charge the card exactly once")
def the_provider_charged_once(scene: Scene, provider_stub: ProviderStub) -> None:
    charges = provider_stub.charges_for(scene.payment_id)
    assert len(charges) == 1, f"the provider received {len(charges)} charges, expected 1"
