"""Allure extras that need pytest hooks: run metadata at session start and failure evidence.

The hooks themselves live in tests/conftest.py; this module holds the logic so the conftest
stays short. Nothing here reads or writes credentials: environment.properties lists only
non-secret facts, and every attachment comes from already-masked sources.
"""

import os
import platform
import shutil
from importlib.metadata import version
from pathlib import Path
from typing import Any

import allure
import pytest
from playwright.sync_api import Page

from tests.config import Settings
from tests.utils import evidence

CATEGORIES = Path(__file__).resolve().parent.parent / "allure" / "categories.json"

# Playwright artifacts worth attaching, by file name inside the per-test output directory.
_BROWSER_ARTIFACTS: dict[str, tuple[str, Any, str | None]] = {
    "test-failed-1.png": ("screenshot", allure.attachment_type.PNG, None),
    "video.webm": ("video", allure.attachment_type.WEBM, None),
    "trace.zip": ("playwright trace (npx playwright show-trace)", "application/zip", "zip"),
}
# Files that would carry typed credentials (network bodies, recorded screen): see `sensitive`.
_CREDENTIAL_CARRIERS = {"video.webm", "trace.zip"}


def write_run_metadata(alluredir: str, settings: Settings) -> None:
    """environment.properties (the report's Environment widget) and categories.json."""
    out = Path(alluredir)
    out.mkdir(parents=True, exist_ok=True)
    props = {
        "Python": platform.python_version(),
        "Playwright": version("playwright"),
        "Browser": "chromium",
        "OS": platform.platform(),
        "Base.URL": settings.base_url,
        "Commit": os.environ.get("GITHUB_SHA", "local")[:12],
        "Run": os.environ.get("GITHUB_RUN_ID", "local"),
    }
    (out / "environment.properties").write_text(
        "".join(f"{key}={value}\n" for key, value in props.items()), encoding="utf-8"
    )
    shutil.copyfile(CATEGORIES, out / "categories.json")


def clear_browser_artifacts(output_dir: str) -> None:
    """Start a run with an empty Playwright output directory (the plugin's own per-worker wipe is
    disabled in tests/ui/conftest.py: under xdist a late worker would delete earlier failures)."""
    shutil.rmtree(output_dir, ignore_errors=True)


def attach_failure_evidence(item: pytest.Item) -> None:
    """Called once per failed test, after its fixtures were torn down (browser files exist)."""
    state = evidence.snapshot()
    if state.request and state.response:
        allure.attach(
            state.request, name="last request", attachment_type=allure.attachment_type.JSON
        )
        allure.attach(
            state.response, name="last response", attachment_type=allure.attachment_type.JSON
        )
    if state.sql:
        allure.attach(state.sql, name="last SQL", attachment_type=allure.attachment_type.TEXT)
        allure.attach(
            state.sql_result or "",
            name="last SQL result",
            attachment_type=allure.attachment_type.TEXT,
        )
    if not isinstance(item, pytest.Function):
        return
    output_dir = item.funcargs.get("output_path")  # only tests that use the `page` fixture
    if not output_dir:
        return
    sensitive = item.get_closest_marker("sensitive") is not None
    for file_name, (label, kind, extension) in _BROWSER_ARTIFACTS.items():
        path = Path(str(output_dir)) / file_name
        if not path.exists():
            continue
        if sensitive and file_name in _CREDENTIAL_CARRIERS:
            path.unlink()  # a test that types credentials keeps only its screenshot
            continue
        allure.attach.file(str(path), name=label, attachment_type=kind, extension=extension)
    page = item.funcargs.get("page")
    if isinstance(page, Page):
        allure.attach(page.url, name="page url", attachment_type=allure.attachment_type.TEXT)
