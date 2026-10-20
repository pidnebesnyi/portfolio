"""Read the app's JSON request log (the file the app writes, see app/request_log.py).

The access line of a request is written after the response is sent, so a test that reads the log
right after its HTTP call may be a moment early: `request()` waits (with a deadline) for the line
that closes the request. What it found is kept as Allure evidence for a failing test.
"""

import json
from pathlib import Path

from pydantic import ValidationError

from tests.models.logs import LogLine
from tests.utils import evidence
from tests.utils.waiting import eventually

ACCESS_EVENT = "http.request"


class AppLog:
    def __init__(self, path: Path) -> None:
        self._path = path

    def text(self) -> str:
        """The whole log, for checks that look at everything (secrets must be nowhere)."""
        return self._path.read_text(encoding="utf-8") if self._path.exists() else ""

    def lines_for(self, request_id: str) -> list[LogLine]:
        """Every line of one request, in the order written. A line cut off by a concurrent write
        is skipped; the next read sees it whole."""
        lines: list[LogLine] = []
        for raw in self.text().splitlines():
            if request_id not in raw:
                continue
            try:
                lines.append(LogLine.model_validate(json.loads(raw)))
            except (ValueError, ValidationError):
                continue
        return [line for line in lines if line.request_id == request_id]

    def request(self, request_id: str) -> list[LogLine]:
        """All lines of the request once its closing access line is there."""

        def closed() -> list[LogLine] | None:
            lines = self.lines_for(request_id)
            return lines if any(line.event == ACCESS_EVENT for line in lines) else None

        try:
            lines = eventually(closed, describe=f"the log of request {request_id}")
        except AssertionError:
            evidence.record_extra(
                "app log lines",
                "\n".join(line.model_dump_json() for line in self.lines_for(request_id)),
            )
            raise
        evidence.record_extra("app log lines", "\n".join(line.model_dump_json() for line in lines))
        return lines
