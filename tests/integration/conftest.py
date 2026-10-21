from collections.abc import Iterator

import pytest

from tests.clients.http import LoggedHttpClient
from tests.clients.provider_stub import ProviderStub
from tests.config import Settings


@pytest.fixture(scope="session")
def provider_stub(settings: Settings) -> Iterator[ProviderStub]:
    client = LoggedHttpClient(settings.provider_url, settings.http_timeout_s, settings.target_env)
    yield ProviderStub(client)
    client.close()
