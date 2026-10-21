"""Which environment the suite points at, and what it may do there.

TARGET_ENV names the environment under test. Staging and production are read-only: nothing that
creates, changes or deletes data may run against them. Two independent lines of defence enforce it:
destructive tests are skipped at collection (tests/conftest.py), and the HTTP client and the
database helper refuse to write, so a test nobody marked still cannot change anything.
"""

from collections.abc import Iterable
from urllib.parse import urlsplit

# True = production-like, read-only. A new environment must be listed here on purpose.
ENVIRONMENTS: dict[str, bool] = {
    "local": False,
    "ci": False,
    "staging": True,
    "production": True,
}
DEFAULT_ENV = "local"

# Fixtures that create or delete data through the API. Anything that depends on them (merchant,
# merchant_page, api, ...) has them in its fixture closure, so the list stays short. admin_api is
# here because it can create and delete merchants: a test that takes it is assumed to use that.
DATA_FIXTURES = frozenset({"merchant_factory", "payment_factory", "admin_api"})
# Gherkin scenarios get their steps' fixtures at run time, so those never show in the closure;
# every scenario builds its data through the factories.
GHERKIN_DIR = "tests/bdd/"

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# POST endpoints that only check credentials and change nothing: the admin session login.
NON_MUTATING_POSTS = frozenset({"/auth/login", "/auth/2fa"})


class ReadOnlyEnvironmentError(RuntimeError):
    """A write was attempted against an environment that must not be changed."""


def validate_env(name: str) -> str:
    if name not in ENVIRONMENTS:
        raise ValueError(f"unknown TARGET_ENV {name!r}, expected one of {sorted(ENVIRONMENTS)}")
    return name


def is_read_only(env: str) -> bool:
    return ENVIRONMENTS[validate_env(env)]


def is_destructive(fixture_names: Iterable[str], marker_names: Iterable[str], nodeid: str) -> bool:
    """A test changes data when it says so (@pytest.mark.destructive), when its fixture closure
    includes a data-creating fixture, or when it is a Gherkin scenario."""
    return (
        "destructive" in set(marker_names)
        or not DATA_FIXTURES.isdisjoint(fixture_names)
        or nodeid.startswith(GHERKIN_DIR)
    )


def skip_reason(env: str) -> str:
    return f"destructive test: TARGET_ENV={env} is read-only (run it against local or ci)"


def check_request(env: str, method: str, path: str) -> None:
    """Raise before a request that could change data leaves for a read-only environment."""
    if not is_read_only(env):
        return
    path = urlsplit(path).path.rstrip("/") or "/"
    if method.upper() in SAFE_METHODS or (method.upper() == "POST" and path in NON_MUTATING_POSTS):
        return
    raise ReadOnlyEnvironmentError(
        f"refused {method.upper()} {path}: TARGET_ENV={env} is read-only, "
        f"only {sorted(SAFE_METHODS)} and POST {sorted(NON_MUTATING_POSTS)} may be sent"
    )


def check_write(env: str, what: str) -> None:
    """Raise before a direct database write against a read-only environment."""
    if is_read_only(env):
        raise ReadOnlyEnvironmentError(f"refused {what}: TARGET_ENV={env} is read-only")
