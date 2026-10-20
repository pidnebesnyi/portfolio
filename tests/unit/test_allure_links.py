"""The Allure suite labels derived from a test's path (tests/utils/allure_links.py).

Pure unit tests: no app, no database, no browser.
"""

import allure
import pytest

from tests.utils.allure_links import area, label_suites

pytestmark = [pytest.mark.regression, area("Reporting")]


@pytest.mark.parametrize(
    ("path", "parent", "suite"),
    [
        ("tests/api/test_refunds.py", "API", "Refunds"),
        ("tests/api/test_health_and_auth.py", "API", "Health and auth"),
        ("tests/db/test_totals_and_cleanup.py", "Database", "Totals and cleanup"),
        ("tests/contract/test_pinned_contract.py", "Contract (OpenAPI)", "Pinned contract"),
        ("tests/integration/test_provider.py", "Provider integration", "Provider"),
        ("tests/ui/test_login.py", "UI", "Login"),
        ("tests/unit/test_build_site.py", "Unit", "Build site"),
    ],
)
@allure.title("A test path maps to the suites {parent} > {suite}")
def test_suites_are_the_layer_and_the_readable_module(
    monkeypatch: pytest.MonkeyPatch, path: str, parent: str, suite: str
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(allure.dynamic, "parent_suite", lambda v: calls.append(("parent", v)))
    monkeypatch.setattr(allure.dynamic, "suite", lambda v: calls.append(("suite", v)))
    label_suites(f"{path}::test_x[param]")
    assert calls == [("parent", parent), ("suite", suite)]
