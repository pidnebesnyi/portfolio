"""The environment guardrails: which requests and tests are allowed per TARGET_ENV."""

import allure
import httpx
import pytest
from pydantic import ValidationError

from tests.clients.http import LoggedHttpClient
from tests.config import TargetSettings
from tests.utils.db import Database
from tests.utils.environment import (
    ENVIRONMENTS,
    ReadOnlyEnvironmentError,
    check_request,
    is_destructive,
    is_read_only,
)

READ_ONLY = [env for env, read_only in ENVIRONMENTS.items() if read_only]
WRITABLE = [env for env, read_only in ENVIRONMENTS.items() if not read_only]


@pytest.mark.regression
@allure.title("Staging and production are read-only, local and ci are not")
def test_only_production_like_environments_are_read_only() -> None:
    assert sorted(READ_ONLY) == ["production", "staging"]
    assert sorted(WRITABLE) == ["ci", "local"]


@pytest.mark.regression
@pytest.mark.parametrize("env", READ_ONLY)
@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "get"])
@allure.title("A read-only environment accepts {method} {env}")
def test_read_only_environment_accepts_reads(env: str, method: str) -> None:
    check_request(env, method, "/payments")


@pytest.mark.regression
@pytest.mark.parametrize("env", READ_ONLY)
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "post"])
@allure.title("A read-only environment refuses {method} {env}")
def test_read_only_environment_refuses_writes(env: str, method: str) -> None:
    with pytest.raises(ReadOnlyEnvironmentError, match=f"TARGET_ENV={env} is read-only"):
        check_request(env, method, "/payments")


@pytest.mark.regression
@pytest.mark.parametrize("env", READ_ONLY)
@pytest.mark.parametrize("path", ["/auth/login", "/auth/2fa", "/auth/login/", "/auth/2fa?x=1"])
@allure.title("A read-only environment accepts the login POST {path} on {env}")
def test_read_only_environment_accepts_the_login_endpoints(env: str, path: str) -> None:
    check_request(env, "POST", path)


@pytest.mark.regression
@pytest.mark.parametrize("path", ["/merchants", "/payments", "/payments/1/refunds", "/auth/other"])
@allure.title("Only the login endpoints are allowlisted for POST: {path}")
def test_other_posts_are_refused(path: str) -> None:
    with pytest.raises(ReadOnlyEnvironmentError):
        check_request("production", "POST", path)


@pytest.mark.regression
@pytest.mark.parametrize("env", WRITABLE)
@allure.title("A writable environment accepts any request: {env}")
def test_writable_environment_accepts_any_request(env: str) -> None:
    check_request(env, "DELETE", "/merchants/1")


@pytest.mark.regression
@allure.title("The HTTP client refuses a write before the request leaves")
def test_client_refuses_a_write_before_sending() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        # A streamed body, like a real response: only then does httpx record `elapsed`.
        return httpx.Response(200, stream=httpx.ByteStream(b"{}"))

    client = LoggedHttpClient("http://app.test", 1.0, "production")
    client._client = httpx.Client(
        base_url="http://app.test", transport=httpx.MockTransport(handler)
    )

    client.request("GET", "/health")
    client.request("POST", "/auth/login", json_body={"email": "a@b.test", "password": "x"})
    with pytest.raises(ReadOnlyEnvironmentError, match="refused DELETE /merchants/1"):
        client.request("DELETE", "/merchants/1")

    assert [(r.method, r.url.path) for r in sent] == [("GET", "/health"), ("POST", "/auth/login")]


@pytest.mark.regression
@allure.title("The database helper refuses a write on a read-only environment")
def test_database_refuses_a_write_before_connecting() -> None:
    # The DSN is unusable on purpose: a refusal must come before any connection attempt.
    with pytest.raises(ReadOnlyEnvironmentError, match="SQL statement"):
        Database("postgresql://nobody@invalid.test/none", "staging").execute("DELETE FROM payments")


@pytest.mark.regression
@pytest.mark.parametrize(
    ("fixtures", "markers", "nodeid", "expected"),
    [
        pytest.param(["settings", "merchant_factory"], [], "tests/api/t.py::a", True, id="factory"),
        pytest.param(["api", "payment_factory"], [], "tests/api/t.py::a", True, id="payments"),
        pytest.param(["admin_api"], [], "tests/api/t.py::a", True, id="admin-api"),
        pytest.param(["settings"], ["destructive"], "tests/api/t.py::a", True, id="marker"),
        pytest.param([], [], "tests/bdd/test_refunds.py::a", True, id="gherkin"),
        pytest.param(["auth_api", "admin_token"], ["smoke"], "tests/api/t.py::a", False, id="auth"),
        pytest.param(["page", "settings"], ["ui"], "tests/ui/t.py::a", False, id="browser"),
    ],
)
@allure.title("A test is destructive when it uses data fixtures or says so: {expected}")
def test_destructive_tests_are_recognised(
    fixtures: list[str], markers: list[str], nodeid: str, expected: bool
) -> None:
    assert is_destructive(fixtures, markers, nodeid) is expected


@pytest.mark.regression
@allure.title("An unknown TARGET_ENV fails fast and names the known values")
def test_unknown_target_env_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_ENV", "prod")

    with pytest.raises(ValidationError, match=r"unknown TARGET_ENV 'prod'.*production"):
        TargetSettings(_env_file=None)
    with pytest.raises(ValueError, match="unknown TARGET_ENV"):
        is_read_only("prod")


@pytest.mark.regression
@allure.title("TARGET_ENV defaults to local")
def test_target_env_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGET_ENV", raising=False)

    assert TargetSettings(_env_file=None).target_env == "local"
