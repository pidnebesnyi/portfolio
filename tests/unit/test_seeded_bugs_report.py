"""scripts/seeded_bugs_report.py (the /bugs/ page) and the Allure labelling of seeded-bug runs.

Pure unit tests: no app, no database, no browser.
"""

from pathlib import Path

import allure
import pytest

from scripts import seeded_bugs_report
from tests.utils.allure_links import area, label_suites, seeded_run

pytestmark = [pytest.mark.regression, area("Reporting")]


def write_junit(path: Path, *, failed: tuple[str, ...] = (), bug: str | None = None) -> None:
    cases = "".join(
        f'<testcase classname="tests.api.test_x" name="{name}">'
        + ("<failure message='boom'/>" if name in failed else "")
        + (f'<properties><property name="seeded_bug" value="{bug}"/></properties>' if bug else "")
        + "</testcase>"
        for name in ("test_a", "test_b")
    )
    path.write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>", encoding="utf-8")


@allure.title("The bugs page links to the Allure report")
def test_page_links_to_the_allure_report(tmp_path: Path) -> None:
    write_junit(tmp_path / "none.xml")
    page = seeded_bugs_report.render_html(seeded_bugs_report.evaluate(tmp_path))
    assert '<a href="report/">Open the failing tests in Allure</a>' in page
    assert 'name="viewport"' in page  # the page must stay readable on a phone


@allure.title("A bug counts as caught when a test marked for it fails")
def test_bug_counts_as_caught_when_a_marked_test_fails(tmp_path: Path) -> None:
    write_junit(tmp_path / "none.xml")
    write_junit(tmp_path / "BUG-1.xml", failed=("test_a",), bug="BUG-1")
    report = seeded_bugs_report.evaluate(tmp_path)
    bug_1 = next(b for b in report["bugs"] if b["id"] == "BUG-1")
    assert bug_1["result"] == "caught"
    assert bug_1["catching_tests"] == ["api.test_x::test_a"]


def record_dynamic(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(allure.dynamic, "parent_suite", lambda v: calls.append(("parent", v)))
    monkeypatch.setattr(allure.dynamic, "suite", lambda v: calls.append(("suite", v)))
    monkeypatch.setattr(allure.dynamic, "parameter", lambda n, v: calls.append((n, v)))
    return calls


@pytest.mark.parametrize(
    ("path", "parent", "suite"),
    [
        ("tests/api/test_refund_concurrency.py", "API", "Refund concurrency"),
        ("tests/api/test_health_and_auth.py", "API", "Health and auth"),
        ("tests/contract/test_openapi.py", "Contract", "OpenAPI contract"),
        ("tests/db/test_totals_and_cleanup.py", "Database", "Totals and cleanup"),
        ("tests/integration/test_provider.py", "Provider integration", "Provider"),
        ("tests/ui/test_login.py", "UI", "Login"),
        ("tests/unit/test_build_site.py", "Unit", "Build site"),
    ],
)
@allure.title("A test path maps to the suites {parent} > {suite}")
def test_suites_are_the_layer_and_the_readable_module(
    monkeypatch: pytest.MonkeyPatch, path: str, parent: str, suite: str
) -> None:
    calls = record_dynamic(monkeypatch)
    label_suites(f"{path}::test_x[param]")
    assert calls == [("parent", parent), ("suite", suite)]


@allure.title("A seeded run keeps the layer in the suite name")
def test_seeded_run_keeps_the_layer_in_the_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = record_dynamic(monkeypatch)
    label_suites("tests/api/test_refund_concurrency.py", "BUG-2")
    assert calls == [
        ("parent", "Seeded bugs on: BUG-2"),
        ("suite", "API · Refund concurrency"),
    ]


@allure.title("A seeded run labels the result with the bug parameter")
def test_seeded_run_labels_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = record_dynamic(monkeypatch)
    seeded_run("BUG-3")
    assert calls == [("seeded bugs", "BUG-3")]


@allure.title("A seeded run does not label results of a correct app")
def test_seeded_run_does_nothing_for_a_correct_app(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = record_dynamic(monkeypatch)
    seeded_run("")
    assert calls == []
