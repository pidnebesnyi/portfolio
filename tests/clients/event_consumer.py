"""Consumer for the payments.events exchange (RabbitMQ), for tests.

Each instance owns an exclusive, auto-delete queue bound to `payment.#`, so parallel tests (and
xdist workers) never take each other's messages; a test filters by the id of its own payment.
It is created before the test acts, so nothing published afterwards is missed.

Waiting is bound to a deadline and blocks on the broker connection, never on a sleep.
"""

import json
import time
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

import allure
import pika
from pika.adapters.blocking_connection import BlockingChannel

from tests.models.events import PaymentEvent
from tests.utils import evidence

EXCHANGE = "payments.events"
SLICE_S = 0.25  # longest single wait on the connection; the deadline is checked between slices


class EventConsumer:
    def __init__(self, url: str) -> None:
        self._connection = pika.BlockingConnection(pika.URLParameters(url))
        self._channel: BlockingChannel = self._connection.channel()
        # Same declaration as the app's: declaring an existing exchange identically is a no-op,
        # and it lets a test bind its queue before the app has published anything.
        self._channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        self.queue: str = self._channel.queue_declare(
            "", exclusive=True, auto_delete=True
        ).method.queue
        self._channel.queue_bind(self.queue, EXCHANGE, "payment.#")
        self._stream: Iterator[Any] = self._channel.consume(
            self.queue, auto_ack=True, inactivity_timeout=SLICE_S
        )
        self.received: list[PaymentEvent] = []

    def close(self) -> None:
        if self._connection.is_open:
            self._channel.cancel()
            self._channel.queue_delete(self.queue)
            self._connection.close()

    def events_for(self, payment_id: UUID) -> list[PaymentEvent]:
        """What has arrived so far for this payment, in publish order."""
        found = [event for event in self.received if event.payment_id == payment_id]
        self._record(found)
        return found

    def wait_for(
        self,
        event_type: str,
        payment_id: UUID,
        *,
        where: Callable[[PaymentEvent], bool] = lambda _: True,
        timeout_s: float = 10.0,
    ) -> PaymentEvent:
        """The first event of this type for this payment (that satisfies `where`); fails when
        none arrives in time."""
        with allure.step(f"wait for {event_type} of payment {payment_id}"):
            deadline = time.monotonic() + timeout_s
            while True:
                for event in self.received:
                    if event.type == event_type and event.payment_id == payment_id and where(event):
                        self.events_for(payment_id)  # keeps them as evidence
                        allure.attach(
                            event.model_dump_json(indent=2),
                            name=f"received {event_type}",
                            attachment_type=allure.attachment_type.JSON,
                        )
                        return event
                if time.monotonic() >= deadline:
                    seen = self.events_for(payment_id)
                    raise AssertionError(
                        f"no {event_type} for payment {payment_id} within {timeout_s} s; "
                        f"received for it: {[e.type for e in seen]}"
                    )
                self._pull_one()

    def _pull_one(self) -> None:
        method, _, body = next(self._stream)
        if method is not None:
            self.received.append(PaymentEvent.model_validate_json(body))

    def _record(self, events: list[PaymentEvent]) -> None:
        evidence.record_extra(
            "received events",
            json.dumps([json.loads(e.model_dump_json()) for e in events], indent=2),
        )
