"""The requirement trace (tests/requirements.py) and its Allure side (tests/utils/allure_links.py).

Collection already fails for an unknown id or an untraced test; these checks cover the other
direction, a requirement no test names, and what the report shows for a traced test.
Pure unit tests: no app, no database, no browser.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import allure
import pytest

from tests.requirements import REQUIREMENTS
from tests.utils.allure_links import annotate, area, requirement

pytestmark = [pytest.mark.regression, area("Reporting")]

TESTS = Path(__file__).resolve().parent.parent
NAMED = re.compile(r'requirement\("([A-Z]+-[A-Z]+)"\)')


class _Node:
    """The part of a pytest item that annotate() reads."""

    def __init__(self, *marks: pytest.MarkDecorator) -> None:
        self._marks = [m.mark for m in marks]

    def iter_markers(self, name: str) -> Iterator[pytest.Mark]:
        return (m for m in self._marks if m.name == name)


@allure.title("Every requirement is named by at least one test, and each has its own issue")
def test_every_requirement_is_covered_by_a_test() -> None:
    named = {
        req_id
        for path in TESTS.rglob("test_*.py")
        if path.parent.name != "unit"
        for req_id in NAMED.findall(path.read_text(encoding="utf-8"))
    }
    assert sorted(REQUIREMENTS.keys() - named) == [], "requirements without a test"
    issues = [req.issue for req in REQUIREMENTS.values()]
    assert len(issues) == len(set(issues)), "two requirements share an issue"


@pytest.mark.parametrize(
    ("repo_url", "issue_link"),
    [
        ("https://github.com/o/r/", ("https://github.com/o/r/issues/37", "PAY-REFUND #37")),
        ("", None),
    ],
    ids=["with-repo-url", "without-repo-url"],
)
@allure.title("A traced test gets the requirement as label and story, and its issue link")
def test_annotate_links_the_requirement_issue(
    monkeypatch: pytest.MonkeyPatch, repo_url: str, issue_link: tuple[str, str] | None
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(allure.dynamic, "feature", lambda v: calls.append(("feature", v)))
    monkeypatch.setattr(allure.dynamic, "label", lambda k, v: calls.append(("label", k, v)))
    monkeypatch.setattr(allure.dynamic, "story", lambda v: calls.append(("story", v)))
    monkeypatch.setattr(
        allure.dynamic, "issue", lambda url, name: calls.append(("issue", url, name))
    )
    annotate(_Node(area("Refunds"), requirement("PAY-REFUND")), repo_url)
    expected = [
        ("feature", "Refunds"),
        ("label", "requirement", "PAY-REFUND"),
        ("story", f"PAY-REFUND: {REQUIREMENTS['PAY-REFUND'].title}"),
    ]
    if issue_link:
        expected.append(("issue", *issue_link))
    assert calls == expected
