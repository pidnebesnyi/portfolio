"""Domain events: after a payment changes, a JSON message goes to a topic exchange.

    exchange   payments.events  (topic, durable)
    routing    payment.created | authorized | captured | voided | failed | refunded
    body       event_id, type, payment_id, merchant_id, amount, refund_amount, refunded_amount,
               status, occurred_at, request_id (the id of the HTTP request that caused it,
               the same one in the X-Request-ID header and in every log line of that request)

Behaviour when the broker is down or slow: the payment request still succeeds (the database is the
source of truth; the broker is not on the correctness path), the failure is logged as
`event.publish_failed`, and the event is lost. This is at-most-once delivery, deliberately. A
production system would write the event to an outbox table in the same transaction as the payment
and publish from there.
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pika

from app import request_log
from app.config import get_settings
from app.db import Payment

EXCHANGE = "payments.events"
TIMEOUT_S = 2.0  # connecting, handshake and the broker's confirm are each capped


def _send(url: str, routing_key: str, body: dict[str, object]) -> None:
    params = pika.URLParameters(url)
    params.socket_timeout = TIMEOUT_S
    params.stack_timeout = TIMEOUT_S
    params.blocked_connection_timeout = TIMEOUT_S
    params.connection_attempts = 1
    connection = pika.BlockingConnection(params)
    try:
        channel = connection.channel()
        channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        # No publisher confirms, on purpose: with them, a publish that races the deletion of
        # another consumer's queue is nacked although every other queue got the message, which
        # would log false failures. Delivery is at-most-once either way (see above).
        channel.basic_publish(
            EXCHANGE,
            routing_key,
            json.dumps(body, separators=(",", ":")).encode(),
            pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
    finally:
        connection.close()


def publish(event_type: str, payment: Payment, *, refund_amount: int | None = None) -> None:
    """Call after the database commit. Never raises."""
    url = get_settings().rabbitmq_url
    if not url:
        return
    event_id = str(uuid4())
    body = {
        "event_id": event_id,
        "type": event_type,
        "payment_id": str(payment.id),
        "merchant_id": str(payment.merchant_id),
        "amount": payment.amount,
        "refund_amount": refund_amount,
        "refunded_amount": payment.refunded_amount,
        "status": payment.status,
        "occurred_at": datetime.now(UTC).isoformat(),
        "request_id": request_log.current_request_id(),
    }
    try:
        _send(url, event_type, body)
    except Exception as exc:  # a broker problem must never fail a payment request
        # Only the exception class: its message may carry connection details.
        request_log.event(
            "event.publish_failed", event_id=event_id, type=event_type, error=type(exc).__name__
        )
    else:
        request_log.event("event.published", event_id=event_id, type=event_type)
