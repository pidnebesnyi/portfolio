"""The API coverage matrix (tests/utils/api_coverage.py): aggregation, matrix, HTML.

Pure unit tests on a small hand-written document: no app, no database, no browser.
"""

import json
from pathlib import Path
from typing import Any

import allure
import pytest

from tests.utils import api_coverage
from tests.utils.allure_links import area
from tests.utils.openapi import OpenApiContract

pytestmark = [pytest.mark.regression, area("API contract")]

SPEC: dict[str, Any] = {
    "paths": {
        "/items": {
            "get": {"responses": {"200": {}, "422": {}}},
            "post": {"responses": {"201": {}, "4XX": {}}},
            "parameters": [],
        },
        "/items/{item_id}": {"get": {"responses": {"200": {}, "404": {}, "default": {}}}},
    }
}


def snap(*observed: tuple[str, str, int, int]) -> dict[str, Any]:
    declared = api_coverage.declared_operations(SPEC)
    return {
        "declared": [[m, p, codes] for (m, p), codes in sorted(declared.items())],
        "observed": [list(o) for o in observed],
    }


@allure.title("Declared operations come from the document, path-level keys are skipped")
def test_declared_operations_come_from_the_document() -> None:
    assert api_coverage.declared_operations(SPEC) == {
        ("GET", "/items"): ["200", "422"],
        ("POST", "/items"): ["201", "4XX"],
        ("GET", "/items/{item_id}"): ["200", "404", "default"],
    }


@allure.title("Worker snapshots are merged: hit counts add up, declared operations are unioned")
def test_merge_adds_hit_counts() -> None:
    merged = api_coverage.merge(
        [
            snap(("GET", "/items", 200, 2)),
            snap(("GET", "/items", 200, 3), ("GET", "/items", 422, 1)),
            {},
        ]
    )

    assert sorted(merged["observed"]) == [["GET", "/items", 200, 5], ["GET", "/items", 422, 1]]
    assert len(merged["declared"]) == 3


@allure.title("The matrix lists every declared status and counts operations and statuses hit")
def test_matrix_lists_hit_and_missed_statuses() -> None:
    matrix = api_coverage.build_matrix(
        snap(("GET", "/items", 200, 4), ("GET", "/items/{item_id}", 404, 1))
    )

    assert matrix["summary"] == {
        "operations_hit": 2,
        "operations_total": 3,
        "statuses_hit": 2,
        "statuses_total": 7,
    }
    by_name = {(op["method"], op["path"]): op for op in matrix["operations"]}
    assert by_name[("GET", "/items")]["statuses"] == [
        {"status": "200", "hits": 4},
        {"status": "422", "hits": 0},
    ]
    assert by_name[("POST", "/items")]["hit"] is False
    assert matrix["undeclared"] == []


@allure.title("A status covered by a range or default key counts for that key")
def test_range_and_default_keys_cover_statuses() -> None:
    matrix = api_coverage.build_matrix(
        snap(("POST", "/items", 409, 1), ("GET", "/items/{item_id}", 500, 2))
    )

    by_name = {(op["method"], op["path"]): op for op in matrix["operations"]}
    assert {s["status"]: s["hits"] for s in by_name[("POST", "/items")]["statuses"]}["4XX"] == 1
    default = {s["status"]: s["hits"] for s in by_name[("GET", "/items/{item_id}")]["statuses"]}
    assert default["default"] == 2
    assert matrix["undeclared"] == []


@allure.title("Observed pairs the document does not declare are listed")
def test_undeclared_pairs_are_listed() -> None:
    matrix = api_coverage.build_matrix(snap(("GET", "/items", 500, 1), ("GET", "/nowhere", 200, 1)))

    assert matrix["undeclared"] == [
        {"method": "GET", "path": "/items", "status": 500, "hits": 1},
        {"method": "GET", "path": "/nowhere", "status": 200, "hits": 1},
    ]
    assert matrix["summary"]["statuses_hit"] == 0


@allure.title("A recorded response is matched to its path template by the checker")
def test_recording_uses_the_checkers_path_template() -> None:
    contract = OpenApiContract(SPEC)

    found = contract.template("get", "/items/3f1c")

    assert found is not None
    assert found[0] == "/items/{item_id}"
    assert contract.template("delete", "/items") is None
    assert contract.template("get", "/unknown") is None


@allure.title("record() and snapshot() keep a per-process tally")
def test_record_and_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_coverage, "_observed", api_coverage.Counter())
    monkeypatch.setattr(api_coverage, "_declared", {})

    api_coverage.note_spec(SPEC)
    api_coverage.record("get", "/items", 200)
    api_coverage.record("GET", "/items", 200)

    assert api_coverage.snapshot()["observed"] == [["GET", "/items", 200, 2]]
    assert len(api_coverage.snapshot()["declared"]) == 3


@allure.title("The HTML page is self-contained and escapes what it prints")
def test_html_is_self_contained_and_escaped() -> None:
    matrix = api_coverage.build_matrix(snap(("GET", "/items", 200, 1)))
    matrix["undeclared"].append({"method": "GET", "path": "/<script>", "status": 500, "hits": 1})

    page = api_coverage.render_html(matrix)

    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "1 / 3" in page
    assert "http://" not in page
    assert "https://" not in page
    assert "<link" not in page


@allure.title("write() puts both files into the results directory")
def test_write_creates_json_and_html(tmp_path: Path) -> None:
    matrix = api_coverage.build_matrix(snap())

    api_coverage.write(tmp_path / "results", matrix)

    written = json.loads((tmp_path / "results" / api_coverage.JSON_NAME).read_text())
    assert written["summary"]["operations_total"] == 3
    assert (tmp_path / "results" / api_coverage.HTML_NAME).read_text().startswith("<!doctype html>")


@allure.title("The summary becomes two Allure environment entries")
def test_summary_properties() -> None:
    matrix = api_coverage.build_matrix(snap(("GET", "/items", 200, 1)))

    assert api_coverage.summary_properties(matrix) == {
        "API.operations.hit": "1 of 3",
        "API.statuses.hit": "1 of 7",
    }
