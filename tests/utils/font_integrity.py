"""Font integrity: the font files a page downloads are byte for byte the ones we expect.

A swapped, truncated or wrongly cached font still renders text, so no `expect(...)` notices.
`FontRecorder` is a `PageHealthMonitor` hook (tests/utils/page_health.py): it fingerprints (SHA-256)
every font response of the page. What is wrong is decided by `font_problems`, plain Python
unit-tested in tests/unit/test_font_integrity.py. The `page_health` fixture (tests/conftest.py)
enforces it at teardown for every browser test; the expected files and hashes are in
tests/ui/design_tokens.py.
"""

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError

FONT_RESOURCE = "font"  # Playwright's resource_type for files loaded through @font-face


@dataclass(frozen=True)
class LoadedFont:
    url: str
    size: int
    sha256: str

    @property
    def path(self) -> str:
        return urlsplit(self.url).path


def fingerprint(url: str, body: bytes) -> LoadedFont:
    return LoadedFont(url=url, size=len(body), sha256=hashlib.sha256(body).hexdigest())


def font_problems(
    loaded: Iterable[LoadedFont], expected: Mapping[str, str], unreadable: Iterable[str] = ()
) -> list[str]:
    """What is wrong with the fonts the page loaded. `expected` maps a URL path to the SHA-256
    of the file served there. A known font with other bytes is a problem, and so is any font
    that is not in `expected`, and any font URL whose bytes could not be read (`unreadable`).
    A page that loads no font has no problem: whether it must load one is for the test to
    assert."""
    problems = []
    for font in loaded:
        want = expected.get(font.path)
        if want is None:
            problems.append(f"unexpected font file {font.url} ({font.size} bytes)")
        elif font.sha256 != want:
            problems.append(
                f"font {font.url} differs from the expected file: "
                f"expected sha256 {want}, actual {font.sha256}, size {font.size} bytes"
            )
    problems.extend(
        f"could not read the bytes of font {url}, so it is unverified" for url in unreadable
    )
    return problems


def format_font_report(problems: Iterable[str]) -> str:
    lines = list(problems)
    if not lines:
        return "All loaded fonts are the expected files."
    return "\n".join([f"{len(lines)} font integrity problem(s) on the page:", *lines])


class FontRecorder:
    """Fingerprints the font responses of one page; add `record` to `PageHealthMonitor.hooks`.

    The body is read inside the handler, not later: Chromium drops it once the page navigates.
    Only fonts are read, and they are small. A response served from the browser's cache again
    (the same font on the next page) has no body to read; it is not a problem when the same URL
    was read before, because the cache returns those bytes."""

    def __init__(self) -> None:
        self.fonts: list[LoadedFont] = []  # one per response whose body could be read
        self._unreadable: list[str] = []

    def record(self, response: Any) -> None:
        if response.request.resource_type != FONT_RESOURCE:
            return
        try:
            self.fonts.append(fingerprint(response.url, response.body()))
        except PlaywrightError:
            self._unreadable.append(response.url)

    @property
    def unreadable(self) -> list[str]:
        """URLs of font responses never read successfully (each listed once)."""
        read = {font.url for font in self.fonts}
        return sorted({url for url in self._unreadable if url not in read})
