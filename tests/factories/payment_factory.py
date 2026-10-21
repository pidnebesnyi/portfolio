from dataclasses import dataclass, field
from uuid import UUID

from tests.clients.payments_api import PaymentsApi
from tests.models.payments import Payment, PaymentStatus
from tests.utils.aaa import arrange
from tests.utils.db import Database

# Each target status is reached by driving the real API, never by writing to the database,
# so a payment built by the factory is always in a state the product can actually produce.
_STEPS_TO_REACH: dict[PaymentStatus, tuple[str, ...]] = {
    PaymentStatus.CREATED: (),
    PaymentStatus.AUTHORIZED: ("authorize",),
    PaymentStatus.FAILED: ("authorize",),  # with a declining card, see create()
    PaymentStatus.VOIDED: ("authorize", "void"),
    PaymentStatus.CAPTURED: ("authorize", "capture"),
    PaymentStatus.PARTIALLY_REFUNDED: ("authorize", "capture", "partial_refund"),
    PaymentStatus.REFUNDED: ("authorize", "capture", "full_refund"),
}


@dataclass
class PaymentFactory:
    """Creates payments for one merchant in any reachable state and removes them afterwards."""

    api: PaymentsApi
    db: Database
    _created: list[UUID] = field(default_factory=list)

    def create(
        self,
        status: PaymentStatus = PaymentStatus.CREATED,
        *,
        amount: int = 1000,
        currency: str = "UAH",
        card_token: str = "tok_success",
    ) -> Payment:
        with arrange(f"create a payment ({status.value}, {amount} {currency})"):
            return self._create(status, amount, currency, card_token)

    def _create(
        self, status: PaymentStatus, amount: int, currency: str, card_token: str
    ) -> Payment:
        if status is PaymentStatus.FAILED:
            card_token = "tok_decline"  # the only way into `failed` is a provider that says no
        payment = self.api.create(amount=amount, currency=currency, card_token=card_token).expect(
            201
        )
        self._created.append(payment.id)
        for step in _STEPS_TO_REACH[status]:
            match step:
                case "authorize" | "capture" | "void":
                    payment = getattr(self.api, step)(payment.id).expect(200)
                case "partial_refund":
                    self.api.refund(payment.id, amount // 4).expect(201)
                case "full_refund":
                    self.api.refund(payment.id, amount).expect(201)
        return self.api.get(payment.id).expect(200)

    def cleanup(self) -> None:
        if self._created:
            # No DELETE /payments in the API; refunds and idempotency keys cascade in the schema.
            self.db.execute("DELETE FROM payments WHERE id = ANY(%s)", (self._created,))
            self._created.clear()
