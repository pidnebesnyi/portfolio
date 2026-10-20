"""Test metadata as pytest markers, turned into Allure labels and links at run time.

    pytestmark = [area("Refunds"), requirement("PAY-REFUND")]
    @seeded_bug("BUG-1")

The helpers return plain pytest marks (typed, strict-marker friendly, usable as decorator or in
`pytestmark`); `annotate()` is called from an autouse fixture and does the Allure side.
Links point at real pages only when REPO_URL is set; otherwise the ids remain as labels.
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
