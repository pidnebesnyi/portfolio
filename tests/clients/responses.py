from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from tests.models.errors import ErrorBody


@dataclass
class ApiResponse[T: BaseModel]:
    """A response whose body has already been validated against a Pydantic model.

    2xx bodies are parsed into `data`, 4xx bodies into `error`. A body that does not match its
    model raises at call time, so a contract drift fails the very first test that sees it.
    """

    raw: httpx.Response
    data: T | None = None
    error: ErrorBody | None = None

    @property
    def status_code(self) -> int:
        return self.raw.status_code

    @property
    def headers(self) -> httpx.Headers:
        return self.raw.headers

    def expect(self, status: int = 200) -> T:
        """Assert the status and return the validated body."""
        assert self.status_code == status, (
            f"expected HTTP {status}, got {self.status_code}: {self.raw.text}"
        )
        assert self.data is not None, f"HTTP {status} response has no body model: {self.raw.text}"
        return self.data

    def expect_no_content(self, status: int = 204) -> None:
        assert self.status_code == status, (
            f"expected HTTP {status}, got {self.status_code}: {self.raw.text}"
        )

    def expect_error(self, status: int, code: str) -> ErrorBody:
        """Assert status and machine-readable error code, return the error body."""
        assert self.status_code == status, (
            f"expected HTTP {status}, got {self.status_code}: {self.raw.text}"
        )
        assert self.error is not None, f"no error body: {self.raw.text}"
        assert self.error.code == code, f"expected error code {code!r}, got {self.error.code!r}"
        return self.error


def parse[T: BaseModel](raw: httpx.Response, model: type[T] | None) -> ApiResponse[T]:
    status = raw.status_code
    try:
        if status >= 500:
            return ApiResponse(raw)  # not an API-shaped body; the caller's assertion will show it
        if status >= 400:
            return ApiResponse(raw, error=ErrorBody.model_validate_json(raw.content))
        if model is None:
            return ApiResponse(raw)
        return ApiResponse(raw, data=model.model_validate_json(raw.content))
    except ValidationError as exc:
        raise AssertionError(
            f"HTTP {status} body violates the response model: {exc}\nbody: {raw.text}"
        ) from exc


def drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}
