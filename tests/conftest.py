"""Fixture layers (outermost first):

  session   settings -> http client -> admin token -> admin API, db
  function  merchant_factory -> merchant (fresh, unique per test) -> payment_factory

Failure evidence (last request/response/SQL, and for UI tests screenshot, trace, video) is
attached to the Allure result by the hooks below; see tests/utils/allure_evidence.py.

Anything a test mutates hangs off a function-scoped merchant, so pytest-xdist workers never
share data and every test can run alone, in any order.
"""

from collections.abc import Generator, Iterator

import pytest

from tests.clients.auth_api import AuthApi
from tests.clients.http import LoggedHttpClient
from tests.clients.merchants_api import MerchantsApi
from tests.clients.payments_api import PaymentsApi
from tests.config import Settings
from tests.factories.merchant_factory import MerchantAccount, MerchantFactory
from tests.factories.payment_factory import PaymentFactory
from tests.utils import evidence
from tests.utils.allure_evidence import (
    attach_failure_evidence,
    clear_browser_artifacts,
    write_run_metadata,
)
from tests.utils.allure_links import annotate
from tests.utils.db import Database
from tests.utils.tokens import totp_code

TIER_MARKERS = {"smoke", "regression", "quarantine"}
FAILED = pytest.StashKey[bool]()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every test belongs to exactly one tier, so -m expressions in CI select what we think."""
    for item in items:
        tiers = TIER_MARKERS & {m.name for m in item.iter_markers()}
        if len(tiers) != 1:
            raise pytest.UsageError(
                f"{item.nodeid} must carry exactly one of {sorted(TIER_MARKERS)}, "
                f"found {sorted(tiers)}"
            )
        # Written into the JUnit XML, so scripts/seeded_bugs_report.py knows who guards which bug.
        for mark in item.iter_markers("seeded_bug"):
            item.user_properties.append(("seeded_bug", str(mark.args[0])))
        # Retries are opt-in per test and must say why (pytest-rerunfailures reads `reruns`).
        for flaky in item.iter_markers("flaky"):
            if not flaky.kwargs.get("reason"):
                raise pytest.UsageError(f"{item.nodeid}: @pytest.mark.flaky needs reason=...")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Once per run, in the xdist controller only: Allure run metadata, clean browser artifacts."""
    config = session.config
    if hasattr(config, "workerinput"):
        return
    if alluredir := config.getoption("allure_report_dir"):
        write_run_metadata(str(alluredir), Settings())
    clear_browser_artifacts(str(config.getoption("output")))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item) -> Generator[None, object, None]:
    """Attach evidence to failed tests. Browser files only exist once the fixtures that record
    them have been torn down, so the attaching happens in the teardown report."""
    report = (yield).get_result()  # type: ignore[attr-defined]
    if report.when in ("setup", "call") and report.failed:
        item.stash[FAILED] = True
    elif report.when == "teardown" and item.stash.get(FAILED, False):
        attach_failure_evidence(item)


# --- session layer -----------------------------------------------------------------------


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def http(settings: Settings) -> Iterator[LoggedHttpClient]:
    client = LoggedHttpClient(settings.base_url, settings.http_timeout_s)
    yield client
    client.close()


@pytest.fixture(scope="session")
def auth_api(http: LoggedHttpClient) -> AuthApi:
    return AuthApi(http)


@pytest.fixture(scope="session")
def admin_token(settings: Settings, auth_api: AuthApi) -> str:
    """Admin login is two steps (password, then TOTP); do it once per xdist worker."""
    step_one = auth_api.login(settings.admin_email, settings.admin_password).expect(200)
    assert step_one.mfa_required is True
    assert step_one.mfa_token
    step_two = auth_api.two_factor(step_one.mfa_token, totp_code(settings.admin_totp_secret))
    return step_two.expect(200).access_token


@pytest.fixture(scope="session")
def admin_api(http: LoggedHttpClient, admin_token: str) -> MerchantsApi:
    return MerchantsApi(http, admin_token)


@pytest.fixture(scope="session")
def db(settings: Settings) -> Database:
    return Database(settings.db_dsn)


@pytest.fixture(autouse=True)
def _allure_metadata(request: pytest.FixtureRequest, settings: Settings) -> None:
    evidence.reset()
    annotate(request.node, settings.repo_url)


# --- function layer ----------------------------------------------------------------------


@pytest.fixture
def merchant_factory(http: LoggedHttpClient, admin_api: MerchantsApi) -> Iterator[MerchantFactory]:
    factory = MerchantFactory(http, admin_api)
    yield factory
    factory.cleanup()


@pytest.fixture
def merchant(merchant_factory: MerchantFactory) -> MerchantAccount:
    return merchant_factory.create("merchant-a")


@pytest.fixture
def other_merchant(merchant_factory: MerchantFactory) -> MerchantAccount:
    return merchant_factory.create("merchant-b")


@pytest.fixture
def api(merchant: MerchantAccount) -> PaymentsApi:
    """Payments API authenticated as this test's own merchant."""
    return merchant.api


@pytest.fixture
def payment_factory(api: PaymentsApi, db: Database) -> Iterator[PaymentFactory]:
    factory = PaymentFactory(api, db)
    yield factory
    factory.cleanup()
