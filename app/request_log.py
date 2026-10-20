"""Request ids and structured logs: one JSON line per request, plus the domain events inside it.

Every line carries the request id, so a test (or a person with grep) can follow one request from
the access line to the payment events it caused. The id is taken from a valid incoming
`X-Request-ID` header, otherwise generated, and is returned in the response header.

What is logged: ids, method, path, status, duration, event names and amounts. Never request or
response bodies, headers, query strings, passwords, tokens or card tokens: the logging calls take
named fields only, so there is nothing generic to leak.

Output goes to stdout (docker logs) and, when LOG_FILE is set, to that file as well, which is how
the test suite reads it.
"""

import json
import logging
import re
import sys
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Request-ID"
# Sent by the middleware when a handler raises before answering. Starlette's own 500 is sent by a
# middleware outside this one, so it would go out without the request id.
_INTERNAL_ERROR = b'{"code":"internal_error","message":"Internal server error"}'
# Only a short, plain token is accepted from the client, so a header cannot forge extra log lines.
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

logger = logging.getLogger("payments.log")

# A mutable dict: handlers running in worker threads add fields (merchant_id) to the same object
# the middleware created, and the middleware reads them back when it writes the access line.
_context: ContextVar[dict[str, Any]] = ContextVar("request_log_context")


def configure(log_file: str = "") -> None:
    """Idempotent; called at startup."""
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(logging.Formatter("%(message)s"))  # the message is already JSON
        logger.addHandler(handler)


def bind(**fields: Any) -> None:
    """Add fields to every line of the current request (no-op outside a request)."""
    if (context := _context.get(None)) is not None:
        context.update({k: str(v) for k, v in fields.items()})


def current_request_id() -> str | None:
    context = _context.get(None)
    return context["request_id"] if context else None


def event(name: str, **fields: Any) -> None:
    """A domain event, e.g. event("refund.accepted", payment_id=..., amount=300)."""
    _write(name, fields)


def _write(name: str, fields: dict[str, Any]) -> None:
    context = _context.get({})
    line = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds"), "event": name}
    line.update({**context, **fields})
    logger.info(json.dumps(line, default=str, separators=(",", ":")))


class RequestLogMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware) so the context variable reaches the route handlers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = MutableHeaders(scope=scope).get(HEADER, "")
        request_id = incoming if _VALID_ID.match(incoming) else uuid4().hex
        context: dict[str, Any] = {"request_id": request_id}
        token = _context.set(context)
        status = 500  # what the client gets if the app raises before answering
        response_started = False
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                MutableHeaders(scope=message)[HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            if not response_started:
                headers = [(b"content-type", b"application/json")]
                await send_with_id(
                    {"type": "http.response.start", "status": 500, "headers": headers}
                )
                await send_with_id({"type": "http.response.body", "body": _INTERNAL_ERROR})
            raise  # still reaches the server's error log with its traceback
        finally:
            _write(
                "http.request",
                {
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            _context.reset(token)
