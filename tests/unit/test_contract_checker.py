"""The OpenAPI response check and the document diff (tests/utils/openapi.py).

A checker that never fails proves nothing, so each kind of violation is produced here on purpose
against a small hand-written document. Pure unit tests: no app, no database, no browser.
"""

import json
from typing import Any

import allure
import pytest

from tests.utils.allure_links import area
from tests.utils.openapi import OpenApiContract, spec_diff

pytestmark = [pytest.mark.regression, area("API contract")]

ITEM_ID = "3f1c2b9e-8a4d-4e7f-9b6a-1c2d3e4f5a6b"
JSON = "application/json"

SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "paths": {
        "/items": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            JSON: {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Item"},
                                }
                            }
                        }
                    }
                }
            }
        },
        "/items/{item_id}": {
            "get": {
                "responses": {
                    "200": {"content": {JSON: {"schema": {"$ref": "#/components/schemas/Item"}}}},
                    "404": {"content": {JSON: {"schema": {"$ref": "#/components/schemas/Error"}}}},
                }
            },
            "delete": {"responses": {"204": {"description": "Deleted"}}},
        },
    },
    "components": {
        "schemas": {
            "Item": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "amount": {"type": "integer"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
                "required": ["id", "amount"],
            },
            # An error body may carry extra keys per error code: the schema opens itself.
            "Error": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
                "additionalProperties": True,
            },
        }
    },
}

CONTRACT = OpenApiContract(SPEC)


def check(
    method: str, path: str, status: int, body: Any = None, content_type: str = JSON
) -> list[str]:
    raw = b"" if body is None else json.dumps(body).encode()
    return CONTRACT.check(method, path, status, content_type, raw)


@allure.title("A response that matches its documented schema has no violations")
def test_documented_response_passes() -> None:
    item = {"id": ITEM_ID, "amount": 100, "created_at": "2026-10-20T10:00:00Z"}
    assert check("GET", f"/items/{ITEM_ID}", 200, item) == []
    assert check("GET", "/items", 200, [item]) == []
    assert check("GET", f"/items/{ITEM_ID}", 404, {"code": "not_found", "message": "x"}) == []
    assert check("DELETE", f"/items/{ITEM_ID}", 204) == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"id": ITEM_ID}, "'amount' is a required property"),
        ({"id": ITEM_ID, "amount": "100"}, "$.amount: '100' is not of type 'integer'"),
        ({"id": "not-a-uuid", "amount": 1}, "$.id: 'not-a-uuid' is not a 'uuid'"),
        (
            {"id": ITEM_ID, "amount": 1, "created_at": "yesterday"},
            "$.created_at: 'yesterday' is not a 'date-time'",
        ),
        (
            {"id": ITEM_ID, "amount": 1, "secret": "x"},
            "Additional properties are not allowed ('secret' was unexpected)",
        ),
    ],
    ids=["missing-field", "wrong-type", "bad-uuid", "bad-date-time", "undocumented-field"],
)
@allure.title("A body that breaks its schema is reported: {expected}")
def test_schema_violation_is_reported(body: dict[str, Any], expected: str) -> None:
    violations = check("GET", f"/items/{ITEM_ID}", 200, body)
    assert len(violations) == 1, violations
    assert violations[0].startswith("GET /items/{item_id} 200: ")
    assert expected in violations[0]


@allure.title("A status code the operation does not document is reported")
def test_undocumented_status_is_reported() -> None:
    assert check("GET", f"/items/{ITEM_ID}", 409, {"code": "conflict"}) == [
        "GET /items/{item_id}: status 409 is not documented (documented: ['200', '404'])"
    ]


@allure.title("A body where none is documented, or a non-JSON body, is reported")
def test_unexpected_body_and_content_type_are_reported() -> None:
    assert check("DELETE", f"/items/{ITEM_ID}", 204, {"deleted": True}) == [
        "DELETE /items/{item_id} 204: a body is returned but none is documented"
    ]
    assert check("GET", "/items", 200, [], content_type="text/html") == [
        "GET /items 200: content type 'text/html', documented application/json"
    ]


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/nowhere"), ("POST", "/items"), ("GET", f"/items/{ITEM_ID}/parts")],
    ids=["unknown-path", "undocumented-method", "longer-path"],
)
@allure.title("A request the document does not describe is not checked: {method} {path}")
def test_undescribed_request_is_not_checked(method: str, path: str) -> None:
    assert CONTRACT.operation(method, path) is None
    assert check(method, path, 404, {"anything": 1}) == []


@allure.title("The document diff lists added, removed and changed keys")
def test_spec_diff_lists_every_change() -> None:
    changed = json.loads(json.dumps(SPEC))
    item = changed["components"]["schemas"]["Item"]
    item["properties"]["amount"]["type"] = "string"
    del item["properties"]["created_at"]
    changed["paths"]["/items"]["post"] = {"responses": {}}
    assert spec_diff(SPEC, changed) == [
        '~ $.components.schemas.Item.properties.amount.type: "integer" -> "string"',
        "- $.components.schemas.Item.properties.created_at",
        "+ $.paths['/items'].post",
    ]
    assert spec_diff(SPEC, json.loads(json.dumps(SPEC))) == []
