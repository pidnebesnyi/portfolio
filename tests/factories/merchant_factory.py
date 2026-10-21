import secrets
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from tests.clients.auth_api import AuthApi
from tests.clients.http import LoggedHttpClient
from tests.clients.merchants_api import MerchantsApi
from tests.clients.payments_api import PaymentsApi
from tests.utils.aaa import arrange


@dataclass(frozen=True)
class MerchantAccount:
    """A merchant created for one test, with a ready-to-use authenticated API client."""

    id: UUID
    name: str
    email: str
    password: str
    token: str
    api: PaymentsApi


@dataclass
class MerchantFactory:
    """Creates merchants through the admin API and deletes every one of them in cleanup().

    Names and emails are unique per call, so tests running in parallel (pytest-xdist) never
    touch each other's data.
    """

    http: LoggedHttpClient
    admin: MerchantsApi
    _created: list[UUID] = field(default_factory=list)

    def create(self, label: str = "qa") -> MerchantAccount:
        with arrange(f"create a merchant ({label})"):
            return self._create(label)

    def _create(self, label: str) -> MerchantAccount:
        suffix = uuid4().hex[:10]
        email = f"{label}-{suffix}@lab.test"
        password = secrets.token_urlsafe(16)  # random per merchant; never a literal in the repo
        merchant = self.admin.create(f"{label} {suffix}", email, password).expect(201)
        self._created.append(merchant.id)
        login = AuthApi(self.http).login(email, password).expect(200)
        assert login.access_token is not None
        return MerchantAccount(
            id=merchant.id,
            name=merchant.name,
            email=email,
            password=password,
            token=login.access_token,
            api=PaymentsApi(self.http, login.access_token),
        )

    def cleanup(self) -> None:
        # Reverse order; accept 404 so a test that deleted its own merchant still tears down.
        for merchant_id in reversed(self._created):
            response = self.admin.delete(merchant_id)
            assert response.status_code in (204, 404), response.raw.text
        self._created.clear()
