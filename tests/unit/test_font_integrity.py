"""Which font files a page may download, and how a font response is read
(tests/utils/font_integrity.py).

Pure unit tests: no app, no browser. The recorder is fed stand-in responses.
"""

import hashlib
from types import SimpleNamespace

import allure
import pytest
from playwright.sync_api import Error as PlaywrightError

from tests.utils.allure_links import area
from tests.utils.font_integrity import (
    FontRecorder,
    fingerprint,
    font_problems,
    format_font_report,
)

pytestmark = [pytest.mark.regression, area("Reporting")]

BASE = "http://app:8000"
FONT_PATH = "/static/fonts/inter-latin-400-normal.woff2"
FONT_URL = BASE + FONT_PATH
FONT_BYTES = b"wOF2 the expected font"
EXPECTED = {FONT_PATH: hashlib.sha256(FONT_BYTES).hexdigest()}


def reply(url: str, body: bytes | Exception, kind: str = "font") -> SimpleNamespace:
    """What the recorder reads from a Playwright Response."""

    def read() -> bytes:
        if isinstance(body, Exception):
            raise body
        return body

    return SimpleNamespace(url=url, request=SimpleNamespace(resource_type=kind), body=read)


@allure.title("The expected font file, byte for byte, is no problem")
def test_the_expected_font_is_no_problem() -> None:
    assert font_problems([fingerprint(FONT_URL + "?v=1", FONT_BYTES)], EXPECTED) == []


@allure.title("A known font served with other bytes is reported with both hashes and the size")
@pytest.mark.parametrize(
    "served", [b"wOF2 another font", FONT_BYTES[:-5], b""], ids=["swapped", "truncated", "empty"]
)
def test_a_known_font_with_other_bytes_is_reported(served: bytes) -> None:
    problems = font_problems([fingerprint(FONT_URL, served)], EXPECTED)

    assert len(problems) == 1
    assert FONT_URL in problems[0]
    assert EXPECTED[FONT_PATH] in problems[0]
    assert hashlib.sha256(served).hexdigest() in problems[0]
    assert f"{len(served)} bytes" in problems[0]


@allure.title("A font file that is not in the expected set is reported, whatever its bytes")
def test_an_unknown_font_file_is_reported() -> None:
    other = BASE + "/static/fonts/other.woff2"

    problems = font_problems([fingerprint(other, FONT_BYTES)], EXPECTED)

    assert problems == [f"unexpected font file {other} ({len(FONT_BYTES)} bytes)"]


@allure.title("The same bytes served from another path are an unexpected font file")
def test_the_expected_bytes_at_another_path_are_unexpected() -> None:
    elsewhere = BASE + "/assets/inter.woff2"

    assert len(font_problems([fingerprint(elsewhere, FONT_BYTES)], EXPECTED)) == 1


@allure.title("A page that loads no font has no font problem")
def test_no_font_loaded_is_no_problem() -> None:
    assert font_problems([], EXPECTED) == []
    assert format_font_report([]) == "All loaded fonts are the expected files."


@allure.title("Every problem is listed, and a font that could not be read is one of them")
def test_all_problems_are_listed_in_the_report() -> None:
    loaded = [fingerprint(FONT_URL, b"x"), fingerprint(BASE + "/f.woff2", b"y")]

    problems = font_problems(loaded, EXPECTED, unreadable=[BASE + "/g.woff2"])
    report = format_font_report(problems)

    assert len(problems) == 3
    assert report.splitlines()[0] == "3 font integrity problem(s) on the page:"
    assert report.count("\n") == 3


@allure.title("The recorder keeps only font responses and fingerprints their bytes")
def test_the_recorder_keeps_only_fonts() -> None:
    recorder = FontRecorder()

    recorder.record(reply(BASE + "/ui/login", b"<html>", kind="document"))
    recorder.record(reply(BASE + "/app.js", b"x", kind="script"))
    recorder.record(reply(FONT_URL, FONT_BYTES))

    assert recorder.fonts == [fingerprint(FONT_URL, FONT_BYTES)]
    assert recorder.fonts[0].path == FONT_PATH
    assert recorder.unreadable == []


@allure.title("A repeat that comes from the browser cache is fine once the font was read")
def test_a_cached_repeat_is_fine_after_a_successful_read() -> None:
    recorder = FontRecorder()
    gone = PlaywrightError("No resource with given identifier found")

    recorder.record(reply(FONT_URL, FONT_BYTES))
    recorder.record(reply(FONT_URL, gone))

    assert recorder.unreadable == []
    assert font_problems(recorder.fonts, EXPECTED, recorder.unreadable) == []


@allure.title("A font that was never readable is reported as unverified, not skipped")
def test_a_font_never_readable_is_reported() -> None:
    recorder = FontRecorder()

    recorder.record(reply(FONT_URL, PlaywrightError("No resource with given identifier found")))

    assert recorder.unreadable == [FONT_URL]
    assert len(font_problems(recorder.fonts, EXPECTED, recorder.unreadable)) == 1
