"""Fixture layers (outermost first):

  session   settings -> OpenAPI document -> http client -> admin token -> admin API, db
  function  merchant_factory -> merchant (fresh, unique per test) -> payment_factory

Failure evidence (last request/response/SQL, and for UI tests screenshot, trace, video) is
attached to the Allure result by the hooks below; see tests/utils/allure_evidence.py.

Anything a test mutates hangs off a function-scoped merchant, so pytest-xdist workers never
share data and every test can run alone, in any order.
"""

from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.clients.auth_api import AuthApi
from tests.clients.http import LoggedHttpClient
from tests.clients.merchants_api import MerchantsApi
from tests.clients.payments_api import PaymentsApi
from tests.config import Settings
from tests.factories.merchant_factory import MerchantAccount, MerchantFactory
from tests.factories.payment_factory import PaymentFactory
from tests.requirements import REQUIREMENTS
from tests.utils import evidence
from tests.utils.aaa import set_test_body_running
from tests.utils.allure_evidence import (
    attach_failure_evidence,
    clear_browser_artifacts,
    write_run_metadata,
)
from tests.utils.allure_links import annotate, label_suites
from tests.utils.app_log import AppLog
from tests.utils.db import Database
from tests.utils.openapi import OpenApiContract
from tests.utils.tokens import totp_code

TIER_MARKERS = {"smoke", "regression"}
FAILED = pytest.StashKey[bool]()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every test belongs to exactly one tier, so -m expressions in CI select what we think,
    has an Allure title, and (outside tests/unit) traces to a known requirement."""
    for item in items:
        tiers = TIER_MARKERS & {m.name for m in item.iter_markers()}
        if len(tiers) != 1:
            raise pytest.UsageError(
                f"{item.nodeid} must carry exactly one of {sorted(TIER_MARKERS)}, "
                f"found {sorted(tiers)}"
            )
        # The report reads like prose, not function names (allure-pytest's own lookup of the title).
        if not getattr(getattr(item, "obj", None), "__allure_display_name__", None):
            raise pytest.UsageError(f"{item.nodeid} needs an Allure title: add @allure.title(...)")
        # The requirement trace (tests/requirements.py); unit tests check tooling, not the product.
        req_ids = {str(m.args[0]) for m in item.iter_markers("requirement")}
        if unknown := sorted(req_ids - REQUIREMENTS.keys()):
            raise pytest.UsageError(
                f"{item.nodeid}: unknown requirement {unknown}, add it to tests/requirements.py"
            )
        if not req_ids and not item.nodeid.startswith("tests/unit/"):
            raise pytest.UsageError(f"{item.nodeid} needs a requirement: add requirement(...)")
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
def pytest_runtest_call(item: pytest.Item) -> Generator[None, object, None]:
    """Mark the test body, so requests made in it are labelled `Act:` (tests/utils/aaa.py).
    Gherkin scenarios already say Given / When / Then, so they keep their own structure."""
    set_test_body_running(not item.nodeid.startswith("tests/bdd/"))
    try:
        yield
    finally:
        set_test_body_running(False)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item) -> Generator[None, object, None]:
    """Attach evidence to failed tests. Browser files only exist once the fixtures that record
    them have been torn down, so the attaching happens in the teardown report."""
    report = (yield).get_result()
    if report.when in ("setup", "call") and report.failed:
        item.stash[FAILED] = True
    elif report.when == "teardown" and item.stash.get(FAILED, False):
        attach_failure_evidence(item)


# --- session layer -----------------------------------------------------------------------


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def openapi_spec(settings: Settings) -> dict[str, Any]:
    """The OpenAPI document the running service publishes about itself."""
    with httpx.Client(base_url=settings.base_url, trust_env=False) as client:
        response = client.get("/openapi.json", timeout=settings.http_timeout_s)
    response.raise_for_status()
    spec: dict[str, Any] = response.json()
    return spec


@pytest.fixture(scope="session")
def http(settings: Settings, openapi_spec: dict[str, Any]) -> Iterator[LoggedHttpClient]:
    """Every response through this client is checked against the service's OpenAPI document."""
    client = LoggedHttpClient(
        settings.base_url, settings.http_timeout_s, contract=OpenApiContract(openapi_spec)
    )
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


@pytest.fixture(scope="session")
def app_log(settings: Settings) -> AppLog:
    """The app's JSON request log; tests that need it skip when APP_LOG_FILE is not set."""
    if not settings.app_log_file:
        pytest.skip("APP_LOG_FILE is not set: point it at the file the app writes (LOG_FILE)")
    return AppLog(Path(settings.app_log_file))


@pytest.fixture(autouse=True)
def _allure_metadata(request: pytest.FixtureRequest, settings: Settings) -> None:
    evidence.reset()
    annotate(request.node, settings.repo_url)
    label_suites(request.node.nodeid)


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
