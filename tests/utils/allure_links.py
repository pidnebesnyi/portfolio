"""Test metadata as pytest markers, turned into Allure labels and links at run time.

    pytestmark = [area("Refunds"), requirement("PAY-REFUND")]

The helpers return plain pytest marks (typed, strict-marker friendly, usable as decorator or in
`pytestmark`); `annotate()` is called from an autouse fixture and does the Allure side.
Links point at real pages only when REPO_URL is set; otherwise the ids remain as labels.

`label_suites()` gives the Suites tab two readable levels instead of allure-pytest's package and
module names: the layer (the folder under tests/) and the module ("Refunds"). Dynamic
suite labels replace allure-pytest's defaults, which are only added for a level left unset; this
repo has no test classes, so the default sub suite never appears.
"""

from pathlib import PurePosixPath

import allure
import pytest

# Top-level folder under tests/ -> the layer shown as the parent suite.
LAYERS = {
    "api": "API",
    "db": "Database",
    "integration": "Provider integration",
    "logs": "Logs",
    "ui": "UI",
    "unit": "Unit",
}


def area(name: str) -> pytest.MarkDecorator:
    """Product area; becomes the Allure feature."""
    return pytest.mark.area(name)


def requirement(req_id: str) -> pytest.MarkDecorator:
    """Requirement id this test covers, e.g. PAY-IDEMP."""
    return pytest.mark.requirement(req_id)


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


def label_suites(nodeid: str) -> None:
    """Parent suite = layer, suite = module, e.g. "API" > "Refunds"."""
    path = PurePosixPath(nodeid.split("::")[0])
    layer = LAYERS.get(path.parent.name, path.parent.name)
    module = path.stem.removeprefix("test_").replace("_", " ").capitalize()
    allure.dynamic.parent_suite(layer)
    allure.dynamic.suite(module)
