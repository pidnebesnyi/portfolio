"""scripts/seeded_bugs_report.py (the /bugs/ page) and the Allure labelling of seeded-bug runs.

Pure unit tests: no app, no database, no browser.
"""

from pathlib import Path

import allure
import pytest

from scripts import seeded_bugs_report
from tests.utils.allure_links import area, seeded_run

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


@allure.title("A seeded run labels the result")
def test_seeded_run_labels_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(allure.dynamic, "parent_suite", lambda v: calls.append(("suite", v)))
    monkeypatch.setattr(allure.dynamic, "parameter", lambda n, v: calls.append((n, v)))
    seeded_run("BUG-3")
    assert calls == [("suite", "Seeded bugs on: BUG-3"), ("seeded bugs", "BUG-3")]


@allure.title("A seeded run does not label results of a correct app")
def test_seeded_run_does_nothing_for_a_correct_app(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: str) -> None:
        raise AssertionError("a correct app must not be labelled")

    monkeypatch.setattr(allure.dynamic, "parent_suite", fail)
    monkeypatch.setattr(allure.dynamic, "parameter", fail)
    seeded_run("")
