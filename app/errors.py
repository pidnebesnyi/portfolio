from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorResponse(BaseModel):
    """Uniform error body. Extra keys (e.g. `from`, `action`) are allowed per error code."""

    model_config = {"extra": "allow"}

    code: str
    message: str | None = None


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str | None = None, **extra: Any):
        self.status_code = status_code
        self.body: dict[str, Any] = {"code": code, "message": message, **extra}


# Documented on every route so the OpenAPI document is truthful (API consumers rely on it).
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse, "description": text}
    for code, text in {
        400: "Bad request",
        401: "Missing, invalid or expired token",
        403: "Role not allowed",
        404: "Not found",
        409: "Conflict",
        422: "Validation or business rule error",
    }.items()
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.body)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Framework-level errors (unknown route, wrong method) get the same body shape as ours
        # instead of FastAPI's {"detail": ...}. A malformed JSON body is a validation error (422).
        codes = {400: "bad_request", 404: "not_found", 405: "method_not_allowed"}
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": codes.get(exc.status_code, "http_error"), "message": str(exc.detail)},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
        if any(
            e["loc"][0] == "header" and str(e["loc"][1]).lower() == "idempotency-key"
            for e in errors
        ):
            # A missing/empty key is a client protocol error (400), not a body validation error.
            return JSONResponse(
                status_code=400,
                content={
                    "code": "idempotency_key_required",
                    "message": "Idempotency-Key header is required",
                },
            )
        return JSONResponse(
            status_code=422,
            content={"code": "validation_error", "message": "Invalid request", "errors": errors},
        )
