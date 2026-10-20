from collections.abc import Iterator

import pytest

from tests.clients.http import LoggedHttpClient
from tests.clients.provider_mock_api import ProviderMockApi
from tests.config import Settings


@pytest.fixture(scope="session")
def provider_mock(settings: Settings) -> Iterator[ProviderMockApi]:
    client = LoggedHttpClient(settings.provider_url, settings.http_timeout_s)
    yield ProviderMockApi(client)
    client.close()
