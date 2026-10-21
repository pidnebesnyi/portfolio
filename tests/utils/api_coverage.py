"""Which documented responses did the suite actually see?

The OpenAPI response check (tests/utils/openapi.py) already looks at every response the suite
receives. `record()` is called from there with the matched path template and the status. At the end
of the run the observed pairs are laid against the service's own document: for every operation
and every status code it declares, was that response seen at least once. A declared status nobody
ever provoked is a gap in the suite, and it is visible as a number instead of a feeling.

Under pytest-xdist each worker keeps its own tally and hands a `snapshot()` to the controller
(tests/conftest.py), which `merge()`s them, builds the matrix and writes the files. Everything
after the recording is pure: plain dicts in, plain dicts or text out, so it is unit-tested alone.
"""

import html
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tests.utils.openapi import declared_key

HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")
JSON_NAME = "api-coverage.json"
HTML_NAME = "api-coverage.html"

_observed: Counter[tuple[str, str, int]] = Counter()
_declared: dict[tuple[str, str], list[str]] = {}


def declared_operations(spec: dict[str, Any]) -> dict[tuple[str, str], list[str]]:
    """(METHOD, path template) -> the status keys the document declares for it ("200", "4XX")."""
    return {
        (method.upper(), template): sorted(op.get("responses", {}))
        for template, ops in spec.get("paths", {}).items()
        for method, op in ops.items()
        if method in HTTP_METHODS
    }


def note_spec(spec: dict[str, Any]) -> None:
    """Remember what the document declares, so the matrix can list what was never hit."""
    _declared.update(declared_operations(spec))


def record(method: str, template: str, status: int) -> None:
    _observed[(method.upper(), template, status)] += 1


def snapshot() -> dict[str, Any]:
    """This process's tally as plain lists (it travels through xdist's workeroutput)."""
    return {
        "declared": [[m, p, codes] for (m, p), codes in sorted(_declared.items())],
        "observed": [[m, p, s, n] for (m, p, s), n in sorted(_observed.items())],
    }


def merge(snapshots: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """One snapshot out of many: declared operations are unioned, hit counts are added up."""
    declared: dict[tuple[str, str], list[str]] = {}
    observed: Counter[tuple[str, str, int]] = Counter()
    for part in snapshots:
        for method, path, codes in part.get("declared", []):
            declared[(method, path)] = codes
        for method, path, status, count in part.get("observed", []):
            observed[(method, path, status)] += count
    return {
        "declared": [[m, p, codes] for (m, p), codes in sorted(declared.items())],
        "observed": [[m, p, s, n] for (m, p, s), n in sorted(observed.items())],
    }


def build_matrix(merged: dict[str, Any]) -> dict[str, Any]:
    """The endpoint x status matrix and its summary numbers.

    An observed status counts for the declared key that covers it ("4XX", "default"); one that no
    key covers is listed under `undeclared` (the response check fails those, so it should be empty).
    """
    declared = {(m, p): codes for m, p, codes in merged["declared"]}
    hits: Counter[tuple[str, str, str]] = Counter()
    seen: set[tuple[str, str]] = set()
    undeclared: list[dict[str, Any]] = []
    for method, path, status, count in merged["observed"]:
        codes = declared.get((method, path))
        key = declared_key(dict.fromkeys(codes), status) if codes is not None else None
        if key is None:
            undeclared.append({"method": method, "path": path, "status": status, "hits": count})
        else:
            hits[(method, path, key)] += count
        seen.add((method, path))
    operations = [
        {
            "method": method,
            "path": path,
            "hit": (method, path) in seen,
            "statuses": [{"status": c, "hits": hits[(method, path, c)]} for c in codes],
        }
        for (method, path), codes in sorted(declared.items(), key=lambda i: (i[0][1], i[0][0]))
    ]
    statuses = [s for op in operations for s in op["statuses"]]
    return {
        "summary": {
            "operations_hit": sum(1 for op in operations if op["hit"]),
            "operations_total": len(operations),
            "statuses_hit": sum(1 for s in statuses if s["hits"]),
            "statuses_total": len(statuses),
        },
        "operations": operations,
        "undeclared": undeclared,
    }


def summary_properties(matrix: dict[str, Any]) -> dict[str, str]:
    """The two headline numbers as Allure environment entries."""
    s = matrix["summary"]
    return {
        "API.operations.hit": f"{s['operations_hit']} of {s['operations_total']}",
        "API.statuses.hit": f"{s['statuses_hit']} of {s['statuses_total']}",
    }


_STYLE = """
body { font: 15px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 60rem; padding: 0 1rem;
  color: #1b1f24; background: #fff; }
h1 { font-size: 1.4rem; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #d0d7de;
  vertical-align: top; }
code { font-size: .9em; }
.hit, .miss, .bad { display: inline-block; margin: .1rem .25rem .1rem 0; padding: 0 .45rem;
  border-radius: 4px; font-variant-numeric: tabular-nums; }
.hit { background: #dafbe1; color: #116329; }
.miss { background: #fff1f0; color: #a40e26; }
.bad { background: #a40e26; color: #fff; }
@media (prefers-color-scheme: dark) {
  body { color: #e6edf3; background: #0d1117; }
  th, td { border-color: #30363d; }
  .hit { background: #12341d; color: #7ee787; }
  .miss { background: #3b1219; color: #ffa198; }
}
"""


def render_html(matrix: dict[str, Any]) -> str:
    """A self-contained page (inline CSS, no scripts or external assets)."""
    s = matrix["summary"]
    rows = []
    for op in matrix["operations"]:
        cells = "".join(
            f'<span class="{"hit" if st["hits"] else "miss"}">{html.escape(st["status"])}'
            f"{' x' + str(st['hits']) if st['hits'] else ' not hit'}</span>"
            for st in op["statuses"]
        )
        rows.append(
            f"<tr><td><b>{html.escape(op['method'])}</b></td>"
            f"<td><code>{html.escape(op['path'])}</code></td><td>{cells}</td></tr>"
        )
    extra = ""
    if matrix["undeclared"]:
        items = "".join(
            f'<span class="bad">{html.escape(u["method"])} {html.escape(u["path"])} '
            f"{u['status']} x{u['hits']}</span>"
            for u in matrix["undeclared"]
        )
        extra = f"<h2>Seen but not declared in the document</h2><p>{items}</p>"
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>API coverage</title><style>{_STYLE}</style></head><body>"
        "<h1>API coverage: endpoint by declared status</h1>"
        f"<p>Operations hit: <b>{s['operations_hit']} / {s['operations_total']}</b>. "
        f"Declared statuses hit: <b>{s['statuses_hit']} / {s['statuses_total']}</b>. "
        "Green: the suite received this response at least once (x = how many times). "
        "Red: the document declares it, no test provoked it.</p>"
        "<table><thead><tr><th>Method</th><th>Path</th><th>Declared statuses</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>{extra}</body></html>\n"
    )


def write(out_dir: str | Path, matrix: dict[str, Any]) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / JSON_NAME).write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    (out / HTML_NAME).write_text(render_html(matrix), encoding="utf-8")
