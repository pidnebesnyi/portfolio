"""Direct database access for verification and cleanup. Every query is attached to Allure."""

import json
from typing import Any

import allure
import psycopg
from psycopg.rows import dict_row

from tests.clients.http import mask_json
from tests.utils import evidence
from tests.utils.environment import check_write

# A result longer than this is cut in the attachment only (the test still sees every row).
MAX_ATTACHED_ROWS = 50

# Positional (%s) or named (%(name)s) placeholders; values are never formatted into the SQL text.
Params = tuple[Any, ...] | dict[str, Any]


class Database:
    """One short-lived connection per call, so no transaction is ever left open between tests."""

    def __init__(self, dsn: str, target_env: str) -> None:
        self._dsn = dsn
        self._target_env = target_env

    def fetch_all(self, sql: str, params: Params = ()) -> list[dict[str, Any]]:
        with allure.step("SQL query"):
            allure.attach(sql.strip(), name="sql", attachment_type=allure.attachment_type.TEXT)
            if params:
                allure.attach(
                    repr(params), name="params", attachment_type=allure.attachment_type.TEXT
                )
            with psycopg.connect(self._dsn, row_factory=dict_row, autocommit=True) as conn:
                rows = conn.execute(sql, params).fetchall()
            result = json.dumps(mask_json(rows[:MAX_ATTACHED_ROWS]), indent=2, default=str)
            allure.attach(
                result,
                name=f"result ({len(rows)} rows)",
                attachment_type=allure.attachment_type.JSON,
            )
            evidence.record_sql(sql.strip(), f"{len(rows)} rows\n{result}")
            return rows

    def fetch_value(self, sql: str, params: Params = ()) -> Any:
        rows = self.fetch_all(sql, params)
        assert len(rows) == 1, f"expected exactly one row, got {len(rows)}"
        return next(iter(rows[0].values()))

    def execute(self, sql: str, params: Params = ()) -> None:
        check_write(self._target_env, "SQL statement")
        with allure.step("SQL statement"):
            allure.attach(sql.strip(), name="sql", attachment_type=allure.attachment_type.TEXT)
            with psycopg.connect(self._dsn, autocommit=True) as conn:
                conn.execute(sql, params)
