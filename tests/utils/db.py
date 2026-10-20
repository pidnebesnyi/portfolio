"""Direct database access for verification and cleanup. Every query is attached to Allure."""

from typing import Any

import allure
import psycopg
from psycopg.rows import dict_row


class Database:
    """One short-lived connection per call: trivially thread-safe (the concurrency tests query
    from several threads) and never leaves a transaction open between tests."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with allure.step("SQL query"):
            allure.attach(sql.strip(), name="sql", attachment_type=allure.attachment_type.TEXT)
            if params:
                allure.attach(
                    repr(params), name="params", attachment_type=allure.attachment_type.TEXT
                )
            with psycopg.connect(self._dsn, row_factory=dict_row, autocommit=True) as conn:
                return conn.execute(sql, params).fetchall()

    def fetch_value(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        rows = self.fetch_all(sql, params)
        assert len(rows) == 1, f"expected exactly one row, got {len(rows)}"
        return next(iter(rows[0].values()))

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with allure.step("SQL statement"):
            allure.attach(sql.strip(), name="sql", attachment_type=allure.attachment_type.TEXT)
            with psycopg.connect(self._dsn, autocommit=True) as conn:
                conn.execute(sql, params)
