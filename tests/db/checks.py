"""Helper shared by the SQL checks.

Each test builds its data through the API for its own merchant and queries only that merchant's
rows, so the checks stay valid while other tests (and xdist workers) write to the same database.
"""

from tests.utils.db import Database, Params


def assert_no_rows(db: Database, sql: str, params: Params, why: str) -> None:
    """Run a 'violations' query: the invariant holds when it returns nothing."""
    rows = db.fetch_all(sql, params)
    assert not rows, f"{why}: {rows}"
