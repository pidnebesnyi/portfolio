"""Schema-driven contract checks: the running app against its own /openapi.json.

Stability choices (a flaky contract test is worse than none):
  * deterministic generation with a fixed seed, so a run is reproducible and CI == local;
  * a small, fixed number of examples per operation (budget, not coverage: the functional
    suites do the deep checks);
  * only checks that must hold for any input: no 5xx, documented status code, documented
    content type, body matches the response schema;
  * a dedicated merchant for the whole run (session-scoped, deleted afterwards). Admin
    endpoints are exercised with that merchant token, so they must answer a documented 403
    and no fuzzed request can create or delete real merchants.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import allure
import pytest
import schemathesis
from schemathesis import checks as sch_checks
from schemathesis.checks import CheckFunction
from schemathesis.config import SchemathesisConfig
from schemathesis.schemas import BaseSchema

from tests.clients.http import LoggedHttpClient
from tests.clients.merchants_api import MerchantsApi
from tests.config import Settings
from tests.factories.merchant_factory import MerchantFactory
from tests.utils.allure_links import area

pytestmark = [pytest.mark.contract, pytest.mark.regression, area("OpenAPI contract")]

# 25 examples x 13 operations keeps the module around ten seconds while still hitting each
# operation's boundary values (Hypothesis always tries them first).
MAX_EXAMPLES = 25
SEED = 20261020

CHECKS: list[CheckFunction] = [
    sch_checks.not_a_server_error,
    sch_checks.status_code_conformance,
    sch_checks.content_type_conformance,
    sch_checks.response_schema_conformance,
]


@pytest.fixture(scope="session")
def contract_token(http: LoggedHttpClient, admin_api: MerchantsApi) -> Iterator[str]:
    factory = MerchantFactory(http, admin_api)
    yield factory.create("contract").token
    factory.cleanup()


@pytest.fixture(scope="session")
def api_schema(settings: Settings) -> BaseSchema:
    config = SchemathesisConfig.from_dict(
        {
            "seed": SEED,
            "generation": {
                "max-examples": MAX_EXAMPLES,
                "deterministic": True,
                # Postgres text cannot store NUL; the API rejects it with a 422, which is
                # documented, but the noise adds nothing to a contract run.
                "allow-x00": False,
                # The Authorization header is injected explicitly below.
                "with-security-parameters": False,
            },
        }
    )
    return schemathesis.openapi.from_url(f"{settings.base_url}/openapi.json", config=config)


schema = schemathesis.pytest.from_fixture("api_schema")


# Outermost: schemathesis wraps the function and drops attributes, and the Allure title is read
# from the wrapper. One pytest item covers every operation (each one is reported as a subtest).
@allure.title("Every API operation conforms to its OpenAPI contract")
@schema.parametrize()
def test_operation_conforms_to_openapi(
    case: schemathesis.Case[Any], settings: Settings, contract_token: str
) -> None:
    response = case.call(
        base_url=settings.base_url, headers={"Authorization": f"Bearer {contract_token}"}
    )
    case.validate_response(response, checks=CHECKS)
