"""The service's own OpenAPI document as a test oracle.

`OpenApiContract.check()` takes one real response and lists every way it breaks the document:
a status code the operation does not declare, a body where none is declared, a non-JSON body,
or a JSON body that does not validate against the declared schema. Objects in the document are
treated as closed (`additionalProperties: false`) unless the schema opens them itself, so a field
the service returns but does not document is a violation too. That is the difference from the
Pydantic models in tests/models: they say what the tests need, this says whether the service's
documentation tells the truth.

`spec_diff()` lists the differences between two documents, one line per changed key.
"""

import copy
import json
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

JSON = "application/json"


def _close_objects(node: Any) -> None:
    """Make every object schema reject undocumented keys, unless it already says otherwise."""
    if isinstance(node, dict):
        if "properties" in node and "additionalProperties" not in node:
            node["additionalProperties"] = False
        for value in node.values():
            _close_objects(value)
    elif isinstance(node, list):
        for value in node:
            _close_objects(value)


def _template_regex(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}/]+\})", template)
    return re.compile(
        "".join("[^/]+" if part.startswith("{") else re.escape(part) for part in parts) + "$"
    )


class OpenApiContract:
    def __init__(self, spec: dict[str, Any]) -> None:
        self._components = copy.deepcopy(spec.get("components", {}))
        _close_objects(self._components)
        # Literal paths first, so /payments never matches a /payments/{id} style template.
        templates = sorted(spec.get("paths", {}).items(), key=lambda item: "{" in item[0])
        self._paths = [(template, _template_regex(template), ops) for template, ops in templates]

    def operation(self, method: str, path: str) -> tuple[str, dict[str, Any]] | None:
        """The documented operation for a request, or None when the document has no such
        method and path (an unknown route or a wrong method has no contract to break)."""
        for template, regex, ops in self._paths:
            if regex.match(path):
                op = ops.get(method.lower())
                return (f"{method.upper()} {template}", op) if op else None
        return None

    def check(
        self, method: str, path: str, status: int, content_type: str | None, body: bytes
    ) -> list[str]:
        found = self.operation(method, path)
        if found is None:
            return []
        name, op = found
        declared = op.get("responses", {})
        response = declared.get(str(status)) or declared.get(f"{str(status)[0]}XX")
        response = response or declared.get("default")
        if response is None:
            return [f"{name}: status {status} is not documented (documented: {sorted(declared)})"]
        content = response.get("content")
        if not content:
            return [f"{name} {status}: a body is returned but none is documented"] if body else []
        if JSON not in content:
            return []  # only JSON bodies are checked
        if not (content_type or "").startswith(JSON):
            return [f"{name} {status}: content type {content_type!r}, documented {JSON}"]
        try:
            instance = json.loads(body)
        except ValueError:
            return [f"{name} {status}: body is not valid JSON"]
        schema = copy.deepcopy(content[JSON].get("schema", {}))
        _close_objects(schema)
        # The response schema refers to "#/components/...": give it the components as siblings.
        validator = Draft202012Validator(
            {**schema, "components": self._components}, format_checker=FormatChecker()
        )
        return [
            f"{name} {status}: {error.json_path}: {error.message}"
            for error in sorted(validator.iter_errors(instance), key=lambda e: e.json_path)
        ]


def _key(path: str, key: str) -> str:
    return f"{path}.{key}" if re.fullmatch(r"\w+", key) else f"{path}[{key!r}]"


def spec_diff(expected: Any, actual: Any, path: str = "$") -> list[str]:
    """`+ key` added, `- key` removed, `~ key: old -> new` changed."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        lines: list[str] = []
        for key in expected.keys() - actual.keys():
            lines.append(f"- {_key(path, key)}")
        for key in actual.keys() - expected.keys():
            lines.append(f"+ {_key(path, key)}")
        for key in expected.keys() & actual.keys():
            lines.extend(spec_diff(expected[key], actual[key], _key(path, key)))
        return sorted(lines, key=lambda line: line[2:])
    if expected != actual:
        return [f"~ {path}: {json.dumps(expected)} -> {json.dumps(actual)}"]
    return []
