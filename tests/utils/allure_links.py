"""Test metadata as pytest markers, turned into Allure labels and links at run time.

    pytestmark = [area("Refunds"), requirement("PAY-REFUND")]
    @seeded_bug("BUG-1")

The helpers return plain pytest marks (typed, strict-marker friendly, usable as decorator or in
`pytestmark`); `annotate()` is called from an autouse fixture and does the Allure side.
Links point at real pages only when REPO_URL is set; otherwise the ids remain as labels.

`seeded_run()` marks results of a run against an app with seeded bugs switched on, so the weekly
seeded-bugs workflow can merge several runs into one Allure report.
"""

import allure
import pytest


def area(name: str) -> pytest.MarkDecorator:
    """Product area; becomes the Allure feature."""
    return pytest.mark.area(name)


def requirement(req_id: str) -> pytest.MarkDecorator:
    """Requirement id this test covers, e.g. PAY-IDEMP."""
    return pytest.mark.requirement(req_id)


def seeded_bug(bug_id: str) -> pytest.MarkDecorator:
    """The test must fail when this bug is injected (also selectable with -m seeded_bug)."""
    return pytest.mark.seeded_bug(bug_id)


def annotate(node: pytest.Item, repo_url: str) -> None:
    repo = repo_url.rstrip("/")
    for mark in node.iter_markers("area"):
        allure.dynamic.feature(mark.args[0])
    for mark in node.iter_markers("requirement"):
        req_id = str(mark.args[0])
        allure.dynamic.label("requirement", req_id)
        if repo:
            allure.dynamic.link(
                f"{repo}/blob/main/docs/test-strategy.md#{req_id.lower()}", name=req_id
            )
    for mark in node.iter_markers("seeded_bug"):
        bug_id = str(mark.args[0])
        allure.dynamic.label("seeded_bug", bug_id)
        if repo:
            allure.dynamic.link(f"{repo}/issues?q={bug_id}", name=bug_id)


def seeded_run(bugs: str) -> None:
    """Tell the report which seeded bug(s) the app was running with; no-op for a correct app.

    The parent suite groups the Suites tab per run. The parameter is what keeps the runs apart:
    Allure derives a test's historyId from its name AND parameters and shows results with equal
    ids as retries of one test, so without it only one of four runs of the same test would show.
    """
    if not bugs:
        return
    allure.dynamic.parent_suite(f"Seeded bugs on: {bugs}")
    allure.dynamic.parameter("seeded bugs", bugs)
