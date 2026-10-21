"""Two authorize calls for one payment, sent together: the provider must be charged once."""

from collections import Counter

import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.clients.provider_stub import ProviderStub
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.allure_links import area, requirement
from tests.utils.parallel import run_together

pytestmark = [pytest.mark.integration, area("Provider integration"), requirement("PAY-PROVIDER")]


@pytest.mark.regression
@allure.title("Parallel authorize calls charge the card once")
def test_parallel_authorize_calls_charge_the_card_once(
    api: PaymentsApi, payment_factory: PaymentFactory, provider_stub: ProviderStub
) -> None:
    payment = payment_factory.create()

    answers = run_together([lambda: api.authorize(payment.id) for _ in range(4)])

    assert Counter(a.status_code for a in answers) == {200: 1, 409: 3}
    assert len(provider_stub.charges_for(payment.id)) == 1
    assert api.get(payment.id).expect(200).status is PaymentStatus.AUTHORIZED
