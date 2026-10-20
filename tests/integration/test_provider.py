"""Authorize against a provider that approves, declines, breaks, hangs or is merely slow.

The mock picks the behaviour from the card token. Every case ends in a final state (authorized or
failed, never left hanging) and is checked from three sides: the API response, the database row,
and what the provider actually received. Time budget: a hung provider costs the app's timeout
(2 s) plus one second of slack, never more.
"""

import time
from collections.abc import Callable

import pytest

from tests.clients.payments_api import PaymentsApi
from tests.clients.provider_mock_api import ProviderMockApi
from tests.config import Settings
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import Payment, PaymentStatus
from tests.utils.allure_links import area, requirement, seeded_bug
from tests.utils.db import Database

pytestmark = [pytest.mark.integration, area("Provider integration"), requirement("PAY-PROVIDER")]

AMOUNT = 1250
CURRENCY = "USD"

# (card token, failure_reason). Each row is one provider behaviour.
FAILURES = [
    pytest.param("tok_decline", "declined", marks=pytest.mark.smoke, id="decline"),
    pytest.param("tok_error", "provider_error", marks=pytest.mark.regression, id="http-500"),
    pytest.param(
        "tok_timeout",
        "provider_timeout",
        marks=[pytest.mark.regression, seeded_bug("BUG-4")],
        id="timeout",
    ),
]


def _db_row(db: Database, payment: Payment) -> dict[str, object]:
    rows = db.fetch_all("SELECT status, failure_reason FROM payments WHERE id = %s", (payment.id,))
    assert len(rows) == 1
    return rows[0]


@pytest.fixture
def authorize(
    api: PaymentsApi, payment_factory: PaymentFactory
) -> Callable[[str], tuple[Payment, float]]:
    """Create a payment with the given card token, authorize it, return (payment, seconds)."""

    def run(card_token: str) -> tuple[Payment, float]:
        payment = payment_factory.create(amount=AMOUNT, currency=CURRENCY, card_token=card_token)
        started = time.monotonic()
        authorized = api.authorize(payment.id).expect(200)
        return authorized, time.monotonic() - started

    return run


@pytest.mark.smoke
def test_approved_charge_authorizes_the_payment(
    authorize: Callable[[str], tuple[Payment, float]],
    api: PaymentsApi,
    db: Database,
    provider_mock: ProviderMockApi,
) -> None:
    payment, _ = authorize("tok_success")

    assert (payment.status, payment.failure_reason) == (PaymentStatus.AUTHORIZED, None)
    assert api.get(payment.id).expect(200).status is PaymentStatus.AUTHORIZED
    assert _db_row(db, payment) == {"status": "authorized", "failure_reason": None}
    # The provider got what the merchant asked for, tagged with our payment id.
    [charge] = provider_mock.charges_for(payment.id)
    assert (charge.amount, charge.currency, charge.card_token) == (AMOUNT, CURRENCY, "tok_success")


@pytest.mark.parametrize(("card_token", "reason"), FAILURES)
def test_provider_failure_ends_in_failed_with_a_reason(
    authorize: Callable[[str], tuple[Payment, float]],
    api: PaymentsApi,
    db: Database,
    provider_mock: ProviderMockApi,
    settings: Settings,
    card_token: str,
    reason: str,
) -> None:
    payment, seconds = authorize(card_token)

    assert (payment.status, payment.failure_reason) == (PaymentStatus.FAILED, reason)
    stored = api.get(payment.id).expect(200)
    assert (stored.status, stored.failure_reason) == (PaymentStatus.FAILED, reason)
    assert _db_row(db, payment) == {"status": "failed", "failure_reason": reason}
    assert len(provider_mock.charges_for(payment.id)) == 1
    # The mock hangs for 10 s on tok_timeout; the app must cut it off at its own timeout.
    assert seconds < settings.provider_timeout_s + 1, f"authorize took {seconds:.1f}s"


@pytest.mark.regression
def test_slow_provider_within_the_timeout_still_succeeds(
    authorize: Callable[[str], tuple[Payment, float]],
    db: Database,
    provider_mock: ProviderMockApi,
    settings: Settings,
) -> None:
    payment, seconds = authorize("tok_slow")

    assert payment.status is PaymentStatus.AUTHORIZED
    assert _db_row(db, payment) == {"status": "authorized", "failure_reason": None}
    assert len(provider_mock.charges_for(payment.id)) == 1
    # Slow means slow (the mock waits 1 s) but below the limit: not mistaken for a timeout.
    assert 0.9 <= seconds < settings.provider_timeout_s


@pytest.mark.regression
@pytest.mark.parametrize("card_token", ["tok_decline", "tok_error", "tok_timeout"])
def test_retrying_a_failed_payment_does_not_charge_again(
    authorize: Callable[[str], tuple[Payment, float]],
    api: PaymentsApi,
    provider_mock: ProviderMockApi,
    card_token: str,
) -> None:
    payment, _ = authorize(card_token)

    api.authorize(payment.id).expect_error(409, "invalid_transition")

    # `failed` is terminal: the second attempt is refused before the provider is called.
    assert len(provider_mock.charges_for(payment.id)) == 1
    assert api.get(payment.id).expect(200).status is PaymentStatus.FAILED
