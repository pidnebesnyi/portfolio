"""Domain events on RabbitMQ: the app publishes to the topic exchange `payments.events` after
the database commit (routing key = event type), and a test consumes them from a private queue.

Absence is proven without waiting for nothing: after the action that must publish nothing, the
test performs one that does and waits for that; the queue keeps publish order, so anything the
first action published would already be in front of it.
"""

import allure
import pytest

from tests.clients.event_consumer import EventConsumer
from tests.clients.payments_api import PaymentsApi
from tests.factories.merchant_factory import MerchantAccount
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.allure_links import area, requirement
from tests.utils.app_log import ACCESS_EVENT, AppLog

pytestmark = [area("Domain events"), requirement("EVT-PUBLISH")]


@pytest.mark.smoke
@allure.title("Capturing a payment publishes one payment.captured with the payment's data")
def test_capture_publishes_one_captured_event(
    api: PaymentsApi,
    merchant: MerchantAccount,
    payment_factory: PaymentFactory,
    event_consumer: EventConsumer,
) -> None:
    payment = payment_factory.create(PaymentStatus.AUTHORIZED, amount=1250)

    captured = api.capture(payment.id)
    event = event_consumer.wait_for("payment.captured", payment.id)

    assert event.payment_id == payment.id
    assert event.merchant_id == merchant.id
    assert (event.amount, event.status) == (1250, PaymentStatus.CAPTURED)
    assert (event.refund_amount, event.refunded_amount) == (None, 0)
    assert event.request_id == captured.headers["X-Request-ID"]
    # Marker: a later event for the same payment, to show nothing else came before it.
    api.refund(payment.id, 50).expect(201)
    event_consumer.wait_for("payment.refunded", payment.id)
    assert [e.type for e in event_consumer.events_for(payment.id)] == [
        "payment.created",
        "payment.authorized",
        "payment.captured",
        "payment.refunded",
    ]


@pytest.mark.regression
@allure.title("A partial refund publishes payment.refunded with the refunded amount")
def test_partial_refund_publishes_the_refunded_amount(
    api: PaymentsApi, payment_factory: PaymentFactory, event_consumer: EventConsumer
) -> None:
    payment = payment_factory.create(PaymentStatus.CAPTURED, amount=1000)

    api.refund(payment.id, 300).expect(201)
    first = event_consumer.wait_for("payment.refunded", payment.id)
    assert (first.refund_amount, first.refunded_amount, first.status) == (
        300,
        300,
        PaymentStatus.PARTIALLY_REFUNDED,
    )

    api.refund(payment.id, 700).expect(201)
    last = event_consumer.wait_for(
        "payment.refunded", payment.id, where=lambda e: e.refunded_amount == 1000
    )
    assert (last.refund_amount, last.status) == (700, PaymentStatus.REFUNDED)


@pytest.mark.regression
@allure.title("A declined authorization publishes payment.failed")
def test_a_declined_authorization_publishes_failed(
    api: PaymentsApi, payment_factory: PaymentFactory, event_consumer: EventConsumer
) -> None:
    payment = payment_factory.create(PaymentStatus.FAILED)

    event = event_consumer.wait_for("payment.failed", payment.id)

    assert event.status is PaymentStatus.FAILED
    assert "payment.authorized" not in [e.type for e in event_consumer.events_for(payment.id)]


@pytest.mark.regression
@allure.title("Rejected requests publish nothing: illegal transition and over-refund")
def test_rejected_requests_publish_nothing(
    api: PaymentsApi, payment_factory: PaymentFactory, event_consumer: EventConsumer
) -> None:
    payment = payment_factory.create(PaymentStatus.CREATED, amount=1000)
    api.capture(payment.id).expect_error(409, "invalid_transition")  # created -> capture
    api.authorize(payment.id).expect(200)  # marker
    event_consumer.wait_for("payment.authorized", payment.id)
    api.capture(payment.id).expect(200)
    api.refund(payment.id, 1001).expect_error(422, "refund_exceeds_amount")
    api.void(payment.id).expect_error(409, "invalid_transition")  # captured -> void
    api.refund(payment.id, 1).expect(201)  # marker
    event_consumer.wait_for("payment.refunded", payment.id)

    assert [e.type for e in event_consumer.events_for(payment.id)] == [
        "payment.created",
        "payment.authorized",
        "payment.captured",
        "payment.refunded",
    ]


@pytest.mark.regression
@allure.title("The event, the response header and the log line share one request id")
def test_event_header_and_log_share_one_request_id(
    api: PaymentsApi,
    payment_factory: PaymentFactory,
    event_consumer: EventConsumer,
    app_log: AppLog,
) -> None:
    payment = payment_factory.create(PaymentStatus.AUTHORIZED)

    response = api.capture(payment.id)
    request_id = response.headers["X-Request-ID"]
    event = event_consumer.wait_for("payment.captured", payment.id)
    lines = app_log.request(request_id)

    assert event.request_id == request_id
    published = next(line for line in lines if line.event == "event.published")
    assert (published.event_id, published.type) == (str(event.event_id), "payment.captured")
    assert [line.event for line in lines][-1] == ACCESS_EVENT
