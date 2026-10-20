"""Thin httpx wrapper: every request becomes one Allure step with request and response attached.

Secrets never reach the report: the Authorization header and sensitive JSON fields are masked
in the attachments (the real request is untouched).

Given the service's OpenAPI document, the client also checks every response against it and fails
the calling test on the first undocumented status, field or shape (tests/utils/openapi.py).
"""

import json
from typing import Any

import allure
import httpx

from tests.utils import evidence
from tests.utils.openapi import OpenApiContract

MASK = "***"
SENSITIVE_JSON_KEYS = frozenset(
    {
        "password",
        "code",
        "access_token",
        "mfa_token",
        "totp_secret",
        "authorization",
        "token",
        "password_hash",
    }
)
# "code" is the one-time code in a request, but the error code in a response, which must show.
RESPONSE_SENSITIVE_JSON_KEYS = SENSITIVE_JSON_KEYS - {"code"}
SENSITIVE_HEADERS = frozenset({"authorization"})


def mask_json(value: Any, keys: frozenset[str] = SENSITIVE_JSON_KEYS) -> Any:
    if isinstance(value, dict):
        return {k: MASK if k in keys else mask_json(v, keys) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_json(v, keys) for v in value]
    return value


def mask_headers(headers: httpx.Headers | dict[str, str]) -> dict[str, str]:
    return {k: MASK if k.lower() in SENSITIVE_HEADERS else v for k, v in headers.items()}


def _pretty(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _body(content: bytes, keys: frozenset[str] = SENSITIVE_JSON_KEYS) -> Any:
    """Body as a masked JSON value when it is JSON, otherwise as text; None when empty."""
    if not content:
        return None
    try:
        return mask_json(json.loads(content), keys)
    except ValueError:
        return content.decode(errors="replace")


def _check_contract(
    contract: OpenApiContract, request: httpx.Request, response: httpx.Response
) -> None:
    violations = contract.check(
        request.method,
        request.url.path,
        response.status_code,
        response.headers.get("content-type"),
        response.content,
    )
    if violations:
        text = "\n".join(violations)
        allure.attach(text, name="OpenAPI violations", attachment_type=allure.attachment_type.TEXT)
        raise AssertionError(f"response does not match the service's OpenAPI document:\n{text}")


class LoggedHttpClient:
    def __init__(
        self, base_url: str, timeout_s: float, contract: OpenApiContract | None = None
    ) -> None:
        # trust_env=False: ignore HTTP(S)_PROXY, a CI proxy must not sit between test and app.
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s, trust_env=False)
        self._contract = contract

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        all_headers = dict(headers or {})
        if token is not None:
            all_headers["Authorization"] = f"Bearer {token}"
        with allure.step(f"{method} {path}"):
            request = self._client.build_request(
                method, path, json=json_body, params=params, headers=all_headers
            )
            request_text = _pretty(
                {
                    "method": request.method,
                    "url": str(request.url),
                    "headers": mask_headers(request.headers),
                    "body": _body(request.content),
                }
            )
            allure.attach(request_text, name="request", attachment_type=allure.attachment_type.JSON)
            response = self._client.send(request)
            response_text = _pretty(
                {
                    "status": response.status_code,
                    "elapsed_ms": round(response.elapsed.total_seconds() * 1000),
                    "headers": mask_headers(response.headers),
                    "body": _body(response.content, RESPONSE_SENSITIVE_JSON_KEYS),
                }
            )
            allure.attach(
                response_text,
                name=f"response {response.status_code}",
                attachment_type=allure.attachment_type.JSON,
            )
            evidence.record_http(request_text, response_text)
            if self._contract is not None:
                _check_contract(self._contract, request, response)
        return response
