"""Thin httpx wrapper: every request becomes one Allure step with request and response attached.

Secrets never reach the report: the Authorization header and sensitive JSON fields are masked
in the attachments (the real request is untouched).
"""

import json
from typing import Any

import allure
import httpx

MASK = "***"
SENSITIVE_JSON_KEYS = frozenset(
    {"password", "code", "access_token", "mfa_token", "totp_secret", "authorization", "token"}
)
SENSITIVE_HEADERS = frozenset({"authorization"})


def mask_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: MASK if k in SENSITIVE_JSON_KEYS else mask_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_json(v) for v in value]
    return value


def mask_headers(headers: httpx.Headers | dict[str, str]) -> dict[str, str]:
    return {k: MASK if k.lower() in SENSITIVE_HEADERS else v for k, v in headers.items()}


def _pretty(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _body(content: bytes) -> Any:
    """Body as a masked JSON value when it is JSON, otherwise as text; None when empty."""
    if not content:
        return None
    try:
        return mask_json(json.loads(content))
    except ValueError:
        return content.decode(errors="replace")


class LoggedHttpClient:
    def __init__(self, base_url: str, timeout_s: float) -> None:
        # trust_env=False: ignore HTTP(S)_PROXY, a CI proxy must not sit between test and app.
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s, trust_env=False)

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
            allure.attach(
                _pretty(
                    {
                        "url": str(request.url),
                        "headers": mask_headers(request.headers),
                        "body": _body(request.content),
                    }
                ),
                name="request",
                attachment_type=allure.attachment_type.JSON,
            )
            response = self._client.send(request)
            allure.attach(
                _pretty(
                    {
                        "status": response.status_code,
                        "elapsed_ms": round(response.elapsed.total_seconds() * 1000),
                        "headers": mask_headers(response.headers),
                        "body": _body(response.content),
                    }
                ),
                name=f"response {response.status_code}",
                attachment_type=allure.attachment_type.JSON,
            )
        return response
