from pytest_bdd import then, when

from tests.bdd.steps.common import Scene
from tests.clients.payments_api import PaymentsApi
from tests.factories.merchant_factory import MerchantAccount
from tests.models.payments import PaymentStatus


@when("another merchant asks for that payment")
def another_merchant_asks(scene: Scene, other_merchant: MerchantAccount) -> None:
    scene.response = other_merchant.api.get(scene.payment_id)


@then("the payment is reported as not found")
def reported_as_not_found(scene: Scene) -> None:
    # 404, not 403: the answer must not confirm that the payment exists.
    scene.response.expect_error(404, "payment_not_found")


@then("the owner still sees the payment unchanged")
def the_owner_still_sees_it(scene: Scene, api: PaymentsApi) -> None:
    stored = api.get(scene.payment_id).expect(200)
    assert (stored.id, stored.status) == (scene.payment_id, PaymentStatus.CREATED)
