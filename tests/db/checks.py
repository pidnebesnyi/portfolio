"""Helper shared by the SQL checks.

Each test builds its data through the API for its own merchant and queries only that merchant's
rows, so the checks stay valid while other tests (and xdist workers) write to the same database.
"""

import allure
from deepdiff import DeepDiff

from tests.utils.db import Database, Params


def assert_no_rows(db: Database, sql: str, params: Params, why: str) -> None:
    """Run a 'violations' query: the invariant holds when it returns nothing."""
    rows = db.fetch_all(sql, params)
    assert not rows, f"{why}: {rows}"


def assert_no_diff(diff: DeepDiff) -> None:
    """The two compared structures are equal; otherwise the diff is attached and is the message."""
    if diff:
        allure.attach(diff.pretty(), name="deepdiff", attachment_type=allure.attachment_type.TEXT)
        allure.attach(
            diff.to_json(indent=2),
            name="deepdiff.json",
            attachment_type=allure.attachment_type.JSON,
        )
    assert not diff, f"API and database differ:\n{diff.pretty()}"
