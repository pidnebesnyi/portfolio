"""Load profile of the payments API: merchants paying, refunding and looking at their payments.

Run (from the repository root, app on localhost:8000, credentials in .env):

    set -a; . ./.env; set +a
    locust -f load/locustfile.py,load/thresholds.py --host http://localhost:8000 \
        --headless -u 20 -r 5 -t 1m --exit-code-on-error 0 --html load-report/report.html

`--exit-code-on-error 0` hands the verdict to thresholds.py (p95 and error rate) instead of
Locust failing the run on the first single error. In CI the same thing runs through
`docker compose --profile load run --rm locust` (see .github/workflows/load.yml).
"""

import base64
import contextlib
import hashlib
import hmac
import json
import os
import random
import secrets
import struct
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from locust import HttpUser, between, task
from locust.exception import StopUser

CURRENCIES = ["UAH", "USD", "EUR"]
# Provider-mock token that always approves. Slow / failing tokens are the integration tests' job;
# a load test that mixes in 10 s timeouts would measure the mock, not the app.
APPROVING_TOKEN = "tok_success"
SETUP_TIMEOUT_S = 15


def totp_code(secret: str, at: float | None = None) -> str:
    """RFC 6238 code (SHA-1, 30 s, 6 digits). Written with the standard library on purpose: the
    stock locust image has no pyotp, and a custom image would be one more thing to maintain."""
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    counter = int((time.time() if at is None else at) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def _json_call(
    host: str, method: str, path: str, body: dict[str, Any] | None, token: str | None
) -> tuple[int, Any]:
    """Setup-only HTTP helper. It bypasses Locust's client, so setup is not in the statistics."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(  # noqa: S310  # host comes from --host, never user input
        host + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=SETUP_TIMEOUT_S) as response:  # noqa: S310
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        return error.code, None


class AdminSession:
    """Admin token shared by all simulated users of this Locust process.

    Logging in needs a password hash check plus a TOTP step, so doing it once instead of once per
    user keeps the setup of 20 users from loading the app before the measurement starts. The token
    lives an hour (app default); it is refreshed after 30 minutes."""

    REFRESH_AFTER_S = 1800

    def __init__(self) -> None:
        self._lock = threading.Lock()  # Locust patches threading: this yields to other greenlets
        self._token: str | None = None
        self._obtained_at = 0.0

    def token(self, host: str) -> str:
        with self._lock:
            if self._token is None or time.monotonic() - self._obtained_at > self.REFRESH_AFTER_S:
                self._token = self._login(host)
                self._obtained_at = time.monotonic()
            return self._token

    @staticmethod
    def _login(host: str) -> str:
        email = os.environ["ADMIN_EMAIL"]
        password = os.environ["ADMIN_PASSWORD"]
        totp_secret = os.environ["ADMIN_TOTP_SECRET"]
        status, step_one = _json_call(
            host, "POST", "/auth/login", {"email": email, "password": password}, None
        )
        if status != 200 or not step_one.get("mfa_token"):
            raise RuntimeError(f"admin login failed: HTTP {status}")
        status, step_two = _json_call(
            host,
            "POST",
            "/auth/2fa",
            {"mfa_token": step_one["mfa_token"], "code": totp_code(totp_secret)},
            None,
        )
        if status != 200:
            raise RuntimeError(f"admin 2FA failed: HTTP {status}")
        return str(step_two["access_token"])


ADMIN = AdminSession()


class MerchantUser(HttpUser):
    """One merchant using the API.

    Setup (not measured): an admin creates a merchant with a random password, the user logs in
    with it, and the merchant is deleted again when the user stops (cascades to its payments).

    Behaviour: after each task the user waits 0.5 to 2 s, so on average one user starts a task
    every 1.25 s. With the task weights below, 20 users produce roughly 15 tasks and 40 requests
    a second. The weights follow what a merchant does most: pay, then look.

        weight 6  pay          create -> authorize -> capture -> partial refund (4 requests)
        weight 2  list         GET /payments (page of 20)
        weight 2  look_up      GET /payments/{id} of a payment this user created
        weight 1  replay       create the same payment twice with one Idempotency-Key

    Requests are named by route template (`/payments/{id}/capture`), so Locust aggregates all
    payments into one row per endpoint instead of one row per payment id.
    """

    wait_time = between(0.5, 2)

    def on_start(self) -> None:
        host = self.host or ""
        email = f"load-{uuid.uuid4().hex[:12]}@lab.test"
        password = secrets.token_urlsafe(16)  # random per user, never a literal in the repo
        started = time.perf_counter()
        try:
            admin_token = ADMIN.token(host)
            status, merchant = _json_call(
                host,
                "POST",
                "/merchants",
                {"name": f"load {email[:17]}", "email": email, "password": password},
                admin_token,
            )
            if status != 201:
                raise RuntimeError(f"merchant creation failed: HTTP {status}")
            status, login = _json_call(
                host, "POST", "/auth/login", {"email": email, "password": password}, None
            )
            if status != 200:
                raise RuntimeError(f"merchant login failed: HTTP {status}")
        except Exception as error:
            # A user that cannot start would otherwise vanish silently and make the run look
            # healthier than it is: record one failed request so the error rate shows it.
            self.environment.events.request.fire(
                request_type="SETUP",
                name="create merchant and log in",
                response_time=(time.perf_counter() - started) * 1000,
                response_length=0,
                exception=error,
                context={},
            )
            raise StopUser from error
        self.merchant_id = str(merchant["id"])
        self.client.headers["Authorization"] = f"Bearer {login['access_token']}"
        self.payment_ids: list[str] = []

    def on_stop(self) -> None:
        merchant_id = getattr(self, "merchant_id", None)
        if merchant_id is None:
            return
        # Best effort: the CI database is thrown away anyway.
        with contextlib.suppress(Exception):
            _json_call(
                self.host or "",
                "DELETE",
                f"/merchants/{merchant_id}",
                None,
                ADMIN.token(self.host or ""),
            )

    # --- helpers ------------------------------------------------------------------------

    def _call(
        self,
        method: str,
        path: str,
        name: str,
        expect_status: int,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expect_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Send one request and mark it failed unless status (and the given JSON fields) match.

        A 2xx with the wrong body is as much a failure as a 500, so it counts in the error rate."""
        with self.client.request(
            method, path, name=name, json=body, headers=headers, catch_response=True
        ) as response:
            if response.status_code != expect_status:
                response.failure(f"expected {expect_status}, got {response.status_code}")
                return None
            try:
                payload: dict[str, Any] = response.json()
            except ValueError:
                response.failure("response is not JSON")
                return None
            for field, value in (expect_json or {}).items():
                if payload.get(field) != value:
                    response.failure(f"{field} is {payload.get(field)!r}, expected {value!r}")
                    return None
            response.success()
            return payload

    def _new_payment_body(self) -> dict[str, Any]:
        return {
            "amount": random.randint(1_000, 50_000),  # 10.00 to 500.00, minor units
            "currency": random.choice(CURRENCIES),
            "description": "load test",
            "card_token": APPROVING_TOKEN,
        }

    def _create(self, body: dict[str, Any], key: str | None = None) -> dict[str, Any] | None:
        payment = self._call(
            "POST",
            "/payments",
            "/payments",
            201,
            body=body,
            headers={"Idempotency-Key": key or uuid.uuid4().hex},
            expect_json={"status": "created"},
        )
        if payment is not None:
            self.payment_ids.append(payment["id"])
            del self.payment_ids[:-50]  # remember the latest 50: enough to read from
        return payment

    # --- tasks ---------------------------------------------------------------------------

    @task(6)
    def pay(self) -> None:
        """The money path. Stops at the first failed step: later steps would only add noise."""
        payment = self._create(self._new_payment_body())
        if payment is None:
            return
        pid = payment["id"]
        if (
            self._call(
                "POST",
                f"/payments/{pid}/authorize",
                "/payments/{id}/authorize",
                200,
                expect_json={"status": "authorized"},
            )
            is None
        ):
            return
        if (
            self._call(
                "POST",
                f"/payments/{pid}/capture",
                "/payments/{id}/capture",
                200,
                expect_json={"status": "captured"},
            )
            is None
        ):
            return
        self._call(
            "POST",
            f"/payments/{pid}/refunds",
            "/payments/{id}/refunds",
            201,
            body={"amount": payment["amount"] // 2},  # half: stays below the paid amount
            expect_json={"payment_status": "partially_refunded"},
        )

    @task(2)
    def list_payments(self) -> None:
        """A merchant's dashboard page: newest 20 payments."""
        self._call("GET", "/payments?limit=20", "/payments?limit=20", 200)

    @task(2)
    def look_up(self) -> None:
        """Open one of the payments this user created (skipped until there is one)."""
        if not self.payment_ids:
            return
        pid = random.choice(self.payment_ids)
        self._call("GET", f"/payments/{pid}", "/payments/{id}", 200, expect_json={"id": pid})

    @task(1)
    def replay(self) -> None:
        """A client retrying a create after a timeout: same key, same body. The second call must
        return the first payment (200), not create another."""
        body = self._new_payment_body()
        key = uuid.uuid4().hex
        first = self._create(body, key)
        if first is None:
            return
        self._call(
            "POST",
            "/payments",
            "/payments (replay)",
            200,
            body=body,
            headers={"Idempotency-Key": key},
            expect_json={"id": first["id"]},
        )
