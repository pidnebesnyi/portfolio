"""scripts/build_site.py: landing page numbers from Allure's summary.json.

Pure unit tests: no app, no database, no browser. See "Running only the unit tests" in
docs/test-strategy.md for how to run them without the stack.
"""

import json
from pathlib import Path

import allure
import pytest

from scripts import build_site
from tests.utils.allure_links import area

REPO = Path(__file__).resolve().parents[2]
RUN_URL = "https://github.com/example/repo/actions/runs/42"
# 2026-10-20 02:41:07 UTC
STOP_MS = 1_792_464_067_000

pytestmark = [pytest.mark.regression, area("Reporting")]


def write_summary(path: Path, *, total: int, passed: int, duration_ms: int = 161_000) -> Path:
    summary = {
        "statistic": {"failed": total - passed, "broken": 0, "skipped": 0, "passed": passed},
        "time": {"start": STOP_MS - duration_ms, "stop": STOP_MS, "duration": duration_ms},
    }
    summary["statistic"]["total"] = total
    path.write_text(json.dumps(summary), encoding="utf-8")
    return path


def make_site(tmp_path: Path, *, with_cv: bool = False) -> Path:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        "<!-- owner note: {{PROFILE_SUMMARY}} -->\n"
        "<p>{{BUILD_TESTS}} tests, {{BUILD_PASS_RATE}}, "
        "{{BUILD_DURATION}}, {{BUILD_LAST_RUN}}</p>\n"
        "<p>{{PROFILE_HEADLINE}}</p><ul>{{BUILD_CV_LINK}}</ul>{{BUILD_RUN_LINK}}\n"
        '<i class="{{BUILD_PASS_CLASS}}"></i>\n'
        "<p>{{BUILD_API_OPERATIONS}} ops, {{BUILD_API_STATUSES}} statuses</p>"
        "{{BUILD_COVERAGE_LINK}}",
        encoding="utf-8",
    )
    (site / "style.css").write_text("body{}", encoding="utf-8")
    if with_cv:
        (site / "cv.pdf").write_bytes(b"%PDF-1.4")
    return site


@allure.title("Run numbers land in the landing page")
def test_numbers_land_in_the_page(tmp_path: Path) -> None:
    summary = write_summary(tmp_path / "summary.json", total=170, passed=170)
    out = tmp_path / "out"

    build_site.build(summary, make_site(tmp_path), out, RUN_URL)

    page = (out / "index.html").read_text(encoding="utf-8")
    assert "170 tests, 100.0 %, 2 min 41 s, 2026-10-20" in page
    assert f'<a href="{RUN_URL}">' in page
    assert 'class="ok"' in page
    assert (out / "style.css").is_file()
    assert not (out / "cv.pdf").exists()


@allure.title("A missing summary shows dashes and the page still builds")
def test_missing_summary_shows_dashes_and_still_builds(tmp_path: Path) -> None:
    out = tmp_path / "out"

    build_site.build(tmp_path / "nope.json", make_site(tmp_path), out, None)

    page = (out / "index.html").read_text(encoding="utf-8")
    assert "— tests, —, —, —" in page
    assert "— ops, — statuses" in page
    assert not (out / "api-coverage.html").exists()
    assert "{{BUILD_" not in page


@pytest.mark.parametrize("content", ["not json", "[]", '{"statistic": 3}', ""])
@allure.title("An unreadable summary is treated as missing: '{content}'")
def test_unreadable_summary_is_treated_as_missing(tmp_path: Path, content: str) -> None:
    path = tmp_path / "summary.json"
    path.write_text(content, encoding="utf-8")

    assert build_site.load_summary(path) is None


@allure.title("A failing run is not rounded up to 100 percent")
def test_a_failing_run_is_not_rounded_up_to_100_percent() -> None:
    summary = {"statistic": {"total": 2000, "passed": 1999}, "time": {}}

    values = build_site.build_values(summary, None, has_cv=False)

    assert values["BUILD_PASS_RATE"] == "99.9 %"
    assert values["BUILD_PASS_CLASS"] == "bad"


@allure.title("The CV link appears only when the PDF exists")
def test_cv_link_only_when_the_pdf_exists(tmp_path: Path) -> None:
    out = tmp_path / "out"
    summary = write_summary(tmp_path / "summary.json", total=1, passed=1)

    build_site.build(summary, make_site(tmp_path, with_cv=True), out, None)

    assert 'href="cv.pdf"' in (out / "index.html").read_text(encoding="utf-8")
    assert (out / "cv.pdf").is_file()


@allure.title("Unset owner placeholders are reported, placeholders in comments are ignored")
def test_unset_owner_placeholders_are_reported_but_comments_are_ignored(tmp_path: Path) -> None:
    out = tmp_path / "out"

    unset = build_site.build(tmp_path / "nope.json", make_site(tmp_path), out, None)

    assert unset == ["PROFILE_HEADLINE"]  # PROFILE_SUMMARY only appears in a comment
    assert "owner note" not in (out / "index.html").read_text(encoding="utf-8")


@allure.title("The profile block is left out until the owner fills it in")
def test_profile_block_is_left_out_until_the_owner_fills_it() -> None:
    template = (
        "<h1>x</h1>\n<!-- profile:start note -->\n<p>{{PROFILE_HEADLINE}}</p>{{BUILD_CV_LINK}}\n"
        "<!-- profile:end -->\n<p>{{BUILD_TESTS}}</p>"
    )

    page, hidden = build_site.drop_unfilled_profile(template)
    filled, nothing_hidden = build_site.drop_unfilled_profile(
        template.replace("{{PROFILE_HEADLINE}}", "QA engineer")
    )

    assert hidden == ["PROFILE_HEADLINE"]
    assert "PROFILE_HEADLINE" not in page
    assert "{{BUILD_TESTS}}" in page
    assert nothing_hidden == []
    assert "QA engineer" in filled


@allure.title("An unknown build placeholder is an error")
def test_unknown_build_placeholder_is_an_error() -> None:
    with pytest.raises(ValueError, match="BUILD_TYPO"):
        build_site.render("{{BUILD_TYPO}}", {"BUILD_TESTS": "1"})


@allure.title("The run URL is HTML-escaped")
def test_run_url_is_escaped() -> None:
    values = build_site.build_values(
        {"statistic": {"total": 1, "passed": 1}, "time": {"stop": STOP_MS, "duration": 1000}},
        'https://x.test/"><script>',
        has_cv=False,
    )

    assert "<script>" not in values["BUILD_RUN_LINK"]


@allure.title("The real template only uses known placeholders")
def test_real_template_only_uses_known_placeholders() -> None:
    """Catches drift between site/index.html and build_site.build_values."""
    template = (REPO / "site" / "index.html").read_text(encoding="utf-8")
    values = build_site.build_values(None, None, has_cv=False)

    page = build_site.render(template, values)  # raises on a BUILD name the script does not know

    assert "{{BUILD_" not in page
    assert build_site.open_placeholders(page) == []  # the profile is filled in
    assert build_site.drop_unfilled_profile(template)[1] == []  # so the build keeps it


def write_coverage(directory: Path, *, with_page: bool = True) -> Path:
    directory.mkdir(exist_ok=True)
    summary = {
        "operations_hit": 12,
        "operations_total": 13,
        "statuses_hit": 20,
        "statuses_total": 61,
    }
    (directory / "api-coverage.json").write_text(json.dumps({"summary": summary}), encoding="utf-8")
    if with_page:
        (directory / "api-coverage.html").write_text("<table></table>", encoding="utf-8")
    return directory / "api-coverage.json"


@allure.title("--coverage fills the two API numbers and publishes the matrix page")
def test_coverage_numbers_and_matrix_page_land_in_the_site(tmp_path: Path) -> None:
    out = tmp_path / "out"
    coverage = write_coverage(tmp_path / "results")

    build_site.build(tmp_path / "nope.json", make_site(tmp_path), out, None, coverage)

    page = (out / "index.html").read_text(encoding="utf-8")
    assert "12 / 13 ops, 20 / 61 statuses" in page
    assert '<a href="api-coverage.html">' in page
    assert (out / "api-coverage.html").read_text(encoding="utf-8") == "<table></table>"


@allure.title("Coverage numbers show without a link when the matrix page is missing")
def test_coverage_without_a_page_has_no_link(tmp_path: Path) -> None:
    out = tmp_path / "out"
    coverage = write_coverage(tmp_path / "results", with_page=False)

    build_site.build(tmp_path / "nope.json", make_site(tmp_path), out, None, coverage)

    page = (out / "index.html").read_text(encoding="utf-8")
    assert "12 / 13 ops" in page
    assert "api-coverage.html" not in page
    assert not (out / "api-coverage.html").exists()


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", "{}", '{"summary": 3}', '{"summary": {"operations_hit": "1"}}'],
)
@allure.title("Unreadable coverage is treated as missing: '{content}'")
def test_unreadable_coverage_is_treated_as_missing(tmp_path: Path, content: str) -> None:
    path = tmp_path / "api-coverage.json"
    path.write_text(content, encoding="utf-8")
    (tmp_path / "api-coverage.html").write_text("x", encoding="utf-8")
    out = tmp_path / "out"

    build_site.build(tmp_path / "nope.json", make_site(tmp_path), out, None, path)

    assert build_site.load_coverage(path) is None
    assert "— ops, — statuses" in (out / "index.html").read_text(encoding="utf-8")
    assert not (out / "api-coverage.html").exists()
    assert build_site.load_coverage(tmp_path / "absent.json") is None
