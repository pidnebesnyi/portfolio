#!/usr/bin/env python3
"""Fill the landing page with the numbers of the latest test run.

Input:  Allure's generated report, `widgets/summary.json` (statistic + time), and the template
        in site/ (index.html, style.css, optional cv.pdf).
Output: the same files in --out-dir, with every `{{BUILD_*}}` value replaced. That directory is
        what the nightly workflow publishes to the root of the gh-pages branch.

Only `{{BUILD_*}}` values are touched. The profile values (`{{PROFILE_*}}`, `{{LINKEDIN_URL}}`,
`{{CONTACT_EMAIL}}`) belong to the site owner. While any of them is unset, the marked profile block
is left out of the page (a public page must never show template braces) and a warning lists them.
A missing or unreadable summary is not an error: the numbers show "—" and the page still builds.

    python scripts/build_site.py --summary allure-report/widgets/summary.json --out-dir site-build
"""

import argparse
import html
import json
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MISSING = "—"
BUILD_PLACEHOLDER = re.compile(r"\{\{(BUILD_[A-Z_]+)\}\}")
ANY_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
PROFILE_BLOCK = re.compile(r"<!-- profile:start.*?<!-- profile:end -->\n?", re.DOTALL)
# Files copied as they are next to the rendered index.html. cv.pdf is optional.
STATIC_FILES = ("style.css", "cv.pdf")


def load_summary(path: Path) -> dict[str, Any] | None:
    """The parsed summary, or None when the file is missing or not what Allure writes."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("statistic"), dict):
        return None
    return data


def format_duration(milliseconds: int) -> str:
    seconds = round(milliseconds / 1000)
    minutes, seconds = divmod(seconds, 60)
    if minutes == 0:
        return f"{seconds} s"
    return f"{minutes} min {seconds:02d} s"


def build_values(
    summary: dict[str, Any] | None, run_url: str | None, has_cv: bool
) -> dict[str, str]:
    """Template placeholder -> HTML-safe replacement text."""
    values = {
        "BUILD_TESTS": MISSING,
        "BUILD_PASS_RATE": MISSING,
        "BUILD_PASS_CLASS": "",
        "BUILD_DURATION": MISSING,
        "BUILD_LAST_RUN": MISSING,
        "BUILD_RUN_LINK": "",
        "BUILD_CV_LINK": '<li><a href="cv.pdf">CV (PDF)</a></li>' if has_cv else "",
    }
    if summary is not None:
        stat = summary["statistic"]
        total = int(stat.get("total", 0))
        passed = int(stat.get("passed", 0))
        values["BUILD_TESTS"] = str(total)
        if total:
            # One decimal, rounded down: 99.96 % must not read as a clean 100 %. Integer
            # arithmetic, because float error would turn 29 of 100 into 28.9 %.
            tenths = passed * 1000 // total
            values["BUILD_PASS_RATE"] = f"{tenths // 10}.{tenths % 10} %"
            values["BUILD_PASS_CLASS"] = "ok" if passed == total else "bad"
        timing = summary.get("time") or {}
        if isinstance(timing.get("duration"), int | float):
            values["BUILD_DURATION"] = format_duration(int(timing["duration"]))
        if isinstance(timing.get("stop"), int | float):
            stopped = datetime.fromtimestamp(timing["stop"] / 1000, tz=UTC)
            values["BUILD_LAST_RUN"] = stopped.strftime("%Y-%m-%d")
            values["BUILD_RUN_LINK"] = _run_link(run_url, stopped)
    return values


def _run_link(run_url: str | None, stopped: datetime) -> str:
    when = stopped.strftime("%H:%M UTC")
    if run_url:
        link = html.escape(run_url, quote=True)
        return f'<span class="note"><a href="{link}">{when}, workflow run</a></span>'
    return f'<span class="note">{when}</span>'


def render(template: str, values: dict[str, str]) -> str:
    """Replace every {{BUILD_*}} value and drop HTML comments (they hold the owner's notes).

    An unknown BUILD name is a bug in the template."""
    body = HTML_COMMENT.sub("", template)
    unknown = sorted(set(BUILD_PLACEHOLDER.findall(body)) - values.keys())
    if unknown:
        raise ValueError(f"template uses unknown build placeholders: {', '.join(unknown)}")
    return BUILD_PLACEHOLDER.sub(lambda match: values[match.group(1)], body)


def drop_unfilled_profile(template: str) -> tuple[str, list[str]]:
    """Remove the profile block while it still holds owner placeholders; return those names."""
    block = PROFILE_BLOCK.search(template)
    if block is None:
        return template, []
    names = open_placeholders(HTML_COMMENT.sub("", block.group(0)))
    unset = [name for name in names if not name.startswith("BUILD_")]
    if not unset:
        return template, []
    return template[: block.start()] + template[block.end() :], unset


def open_placeholders(rendered: str) -> list[str]:
    """Owner-filled placeholders that are still in the page, in order of first appearance."""
    return list(dict.fromkeys(ANY_PLACEHOLDER.findall(rendered)))


def default_run_url() -> str | None:
    server, repo, run_id = (
        os.environ.get(name) for name in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
    )
    return f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else None


def build(summary_path: Path, site_dir: Path, out_dir: Path, run_url: str | None) -> list[str]:
    """Write the finished landing files to out_dir; return the placeholders still unset."""
    summary = load_summary(summary_path)
    if summary is None:
        sys.stderr.write(f"warning: no usable summary at {summary_path}; numbers show {MISSING}\n")
    values = build_values(summary, run_url, has_cv=(site_dir / "cv.pdf").is_file())
    template, hidden = drop_unfilled_profile((site_dir / "index.html").read_text(encoding="utf-8"))
    rendered = render(template, values)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(rendered, encoding="utf-8")
    for name in STATIC_FILES:
        if (site_dir / name).is_file():
            shutil.copyfile(site_dir / name, out_dir / name)
    return hidden + [name for name in open_placeholders(rendered) if name not in hidden]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--summary", type=Path, default=Path("allure-report/widgets/summary.json"))
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    parser.add_argument("--out-dir", type=Path, default=Path("site-build"))
    parser.add_argument("--run-url", default=default_run_url(), help="link to the CI run")
    args = parser.parse_args()

    unset = build(args.summary, args.site_dir, args.out_dir, args.run_url)
    sys.stdout.write(f"wrote {args.out_dir / 'index.html'}\n")
    if unset:
        # A GitHub annotation in CI, a plain line elsewhere. Not an error: the page still works.
        sys.stdout.write(
            f"::warning::profile block left out until these are set: {', '.join(unset)}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
