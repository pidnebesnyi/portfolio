"""Browser fixtures. Playwright itself is configured by pytest-playwright (addopts in
pyproject.toml: trace/video kept on failure, screenshot on failure).

The UI is only verified here, never used to build data: payments and merchants come from the API
fixtures in tests/conftest.py. The exception is the login suite, which exercises the login form.
"""

from typing import Any
from urllib.parse import urlparse

import pytest
from playwright.sync_api import BrowserContext, Page, expect

from tests.config import Settings
from tests.factories.merchant_factory import MerchantAccount

SESSION_COOKIE = "session"


@pytest.fixture(scope="session", autouse=True)
def _expect_timeout() -> None:
    # One global value instead of per-call timeouts: a loaded CI runner running chromium next to
    # the app and the database is slower than a laptop, and expect() returns as soon as it holds.
    expect.set_options(timeout=10_000)


@pytest.fixture(scope="session", autouse=True)
def delete_output_dir() -> None:
    """Replaces the plugin fixture of the same name, which wipes the output directory in every
    xdist worker. The controller clears it once (pytest_sessionstart in tests/conftest.py)."""


@pytest.fixture(scope="session")
def base_url(settings: Settings) -> str:
    return settings.base_url


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    # Fixed locale, timezone and viewport: dates and layout never depend on the machine.
    return {
        **browser_context_args,
        "locale": "en-US",
        "timezone_id": "UTC",
        "viewport": {"width": 1280, "height": 800},
    }


@pytest.fixture
def merchant_page(
    page: Page, context: BrowserContext, merchant: MerchantAccount, settings: Settings
) -> Page:
    """A page already logged in as this test's merchant.

    The session is the merchant's API token placed in the cookie the UI reads, so tests that are
    not about logging in skip the form (and its cost) but still run against the real session.
    """
    context.add_cookies(
        [
            {
                "name": SESSION_COOKIE,
                "value": merchant.token,
                "domain": urlparse(settings.base_url).hostname or "localhost",
                "path": "/ui",
                "httpOnly": True,
                "sameSite": "Lax",
            }
        ]
    )
    return page
