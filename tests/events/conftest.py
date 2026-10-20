from collections.abc import Iterator

import pytest

from tests.clients.event_consumer import EventConsumer
from tests.config import Settings


@pytest.fixture
def event_consumer(settings: Settings) -> Iterator[EventConsumer]:
    """A private queue on the payments.events exchange for this test, deleted afterwards."""
    if not settings.rabbitmq_url:
        pytest.skip("RABBITMQ_URL is not set: point it at the broker the app publishes to")
    consumer = EventConsumer(settings.rabbitmq_url)
    yield consumer
    consumer.close()
