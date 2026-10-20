#!/usr/bin/env python3
"""Did the test suite catch every seeded bug?

Input: one JUnit XML per run, produced with `pytest --junitxml=<dir>/<run>.xml`, where <run> is
`none` (all bugs off) or a bug id such as `BUG-1` (that bug on). Tests that guard a bug carry
`@pytest.mark.seeded_bug("BUG-n")`; tests/conftest.py copies that into the XML as a property.

Rules
  - baseline: with no bug, every test passes (otherwise a "caught" bug could be a plain failure)
  - bug n:    with the bug on, at least one test marked for it FAILS

Output: bugs.json, site/bugs/index.html, a summary on stdout (and on the GitHub job summary).
Exit code 1 when a bug escaped or the baseline is red, so the CI job turns red.

    python scripts/seeded_bugs_report.py --junit-dir junit
"""

import argparse
import html
import json
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BUGS = {
    "BUG-1": "Idempotency replay creates a second payment instead of returning the first.",
    "BUG-2": "A refund larger than the refundable amount is accepted by the app.",
    "BUG-3": "GET /payments/{id} returns another merchant's payment.",
    "BUG-4": "A provider timeout leaves the payment authorized instead of failed.",
}
BASELINE = "none"


@dataclass
class TestResult:
    name: str
    failed: bool
    skipped: bool
    bugs: list[str]


@dataclass
class Run:
    name: str
    present: bool
    results: list[TestResult] = field(default_factory=list)

    @property
    def ran(self) -> list[TestResult]:
        return [t for t in self.results if not t.skipped]

    @property
    def failures(self) -> list[TestResult]:
        return [t for t in self.ran if t.failed]


def read_run(junit_dir: Path, name: str) -> Run:
    path = junit_dir / f"{name}.xml"
    if not path.is_file():
        return Run(name, present=False)
    run = Run(name, present=True)
    # Our own CI artifact, not untrusted input, so the stdlib parser is fine.
    for case in ET.parse(path).getroot().iter("testcase"):  # noqa: S314
        classname = (case.get("classname") or "").removeprefix("tests.")
        bugs = [
            p.get("value", "")
            for p in case.iterfind("properties/property")
            if p.get("name") == "seeded_bug"
        ]
        run.results.append(
            TestResult(
                name=f"{classname}::{case.get('name')}",
                failed=case.find("failure") is not None or case.find("error") is not None,
                skipped=case.find("skipped") is not None,
                bugs=bugs,
            )
        )
    return run


def evaluate(junit_dir: Path) -> dict[str, Any]:
    baseline = read_run(junit_dir, BASELINE)
    baseline_ok = baseline.present and bool(baseline.ran) and not baseline.failures
    bugs = []
    for bug_id, description in BUGS.items():
        run = read_run(junit_dir, bug_id)
        marked = [t for t in run.ran if bug_id in t.bugs]
        catching = [t.name for t in marked if t.failed]
        if not run.present:
            verdict = "no data"
        elif not marked:
            verdict = "no test is marked for this bug"
        elif len(run.failures) == len(run.ran):
            # Everything red usually means the stack never came up, not that the bug was caught.
            verdict = "invalid run (no test passed)"
            catching = []
        else:
            verdict = "caught" if catching else "ESCAPED"
        bugs.append(
            {
                "id": bug_id,
                "description": description,
                "result": verdict,
                "caught": bool(catching),
                "catching_tests": catching,
                "marked_tests": len(marked),
                # Failures of tests that are not marked for this bug: collateral, shown for context.
                "other_failures": len(run.failures) - len(catching),
            }
        )
    caught = sum(1 for b in bugs if b["caught"])
    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "seeded": len(bugs),
        "caught": caught,
        "baseline": {
            "result": "green" if baseline_ok else ("red" if baseline.present else "no data"),
            "tests": len(baseline.ran),
            "failed": len(baseline.failures),
            "failing_tests": [t.name for t in baseline.failures],
        },
        "bugs": bugs,
        "ok": baseline_ok and caught == len(bugs),
    }


CSS = """
:root{--bg:#fff;--fg:#1b1f24;--muted:#59636e;--line:#d1d9e0;--card:#f6f8fa;
--ok:#1a7f37;--bad:#cf222e;--link:#0969da}
@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#8d96a0;
--line:#30363d;--card:#161b22;--ok:#3fb950;--bad:#f85149;--link:#58a6ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:56rem;margin:0 auto;padding:1.5rem 16px 3rem}
h1{font-size:1.6rem;margin:0 0 .25rem}
.lead{font-size:1.15rem;margin:.25rem 0 .5rem}.muted{color:var(--muted);font-size:.9rem}
.ok{color:var(--ok);font-weight:600}.bad{color:var(--bad);font-weight:600}
a{color:var(--link)}
table{width:100%;border-collapse:collapse;margin-top:1.25rem}
th,td{text-align:left;vertical-align:top;padding:.6rem .5rem;border-bottom:1px solid var(--line)}
td:first-child{white-space:nowrap}
th{font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
code{font:.82rem ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}
ul{margin:0;padding-left:1.1rem}
@media(max-width:640px){
thead{display:none}
tr{display:block;background:var(--card);border:1px solid var(--line);border-radius:8px;
margin-bottom:.75rem;padding:.25rem .5rem}
td{display:block;border:0;padding:.3rem 0}
td::before{content:attr(data-label);display:block;font-size:.75rem;
text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
"""


def render_html(report: dict[str, Any]) -> str:
    esc = html.escape
    bugs = report["bugs"]
    baseline = report["baseline"]
    rows = []
    for b in bugs:
        tests = "".join(f"<li><code>{esc(t)}</code></li>" for t in b["catching_tests"])
        cell = f"<ul>{tests}</ul>" if tests else "<span class='muted'>none</span>"
        css = "ok" if b["caught"] else "bad"
        rows.append(
            f"<tr><td data-label='Bug'><b>{esc(b['id'])}</b></td>"
            f"<td data-label='What was broken'>{esc(b['description'])}</td>"
            f"<td data-label='Failing tests with the bug on'>{cell}</td>"
            f"<td data-label='Result'><span class='{css}'>{esc(b['result'])}</span></td></tr>"
        )
    base_css = "ok" if baseline["result"] == "green" else "bad"
    headline_css = "ok" if report["ok"] else "bad"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seeded bugs</title>
<meta name="description"
 content="Bugs injected into the app on purpose, and the tests that catch them.">
<style>{CSS}</style>
</head>
<body>
<main>
<h1>Seeded bugs</h1>
<p class="lead {headline_css}">{report["seeded"]} bugs seeded, {report["caught"]} caught</p>
<p class="muted">Each run starts the app with one defect switched on and runs the API and
integration suites. A bug counts as caught when at least one test marked for it fails.
With no bug switched on, the same suites must be green:
<span class="{base_css}">{esc(str(baseline["result"]))}</span>
({baseline["tests"]} tests, {baseline["failed"]} failed).</p>
<table>
<thead><tr><th>Bug</th><th>What was broken</th>
<th>Failing tests with the bug on</th><th>Result</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
<p class="muted">Updated {esc(str(report["generated_at"]))}. <a href="../">Back to the lab</a></p>
</main>
</body>
</html>
"""


def summary_lines(report: dict[str, Any]) -> list[str]:
    bugs = report["bugs"]
    baseline = report["baseline"]
    lines = [
        f"Seeded bugs: {report['seeded']} seeded, {report['caught']} caught",
        f"Baseline (no bug): {baseline['result']}, {baseline['tests']} tests, "
        f"{baseline['failed']} failed",
    ]
    for b in bugs:
        lines.append(f"  {b['id']}: {b['result']} ({len(b['catching_tests'])} failing)")
        lines.extend(f"      - {t}" for t in b["catching_tests"])
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--junit-dir", type=Path, default=Path("junit"))
    parser.add_argument("--json-out", type=Path, default=Path("bugs.json"))
    parser.add_argument("--site-dir", type=Path, default=Path("site/bugs"))
    args = parser.parse_args()

    report = evaluate(args.junit_dir)
    args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    args.site_dir.mkdir(parents=True, exist_ok=True)
    (args.site_dir / "index.html").write_text(render_html(report))

    lines = summary_lines(report)
    sys.stdout.write("\n".join(lines) + "\n")
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_path, "a") as fh:
            fh.write("```\n" + "\n".join(lines) + "\n```\n")
    if not report["ok"]:
        sys.stderr.write("A seeded bug escaped, or the baseline is red.\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
