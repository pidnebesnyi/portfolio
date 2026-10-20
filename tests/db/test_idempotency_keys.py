"""Idempotency invariants in SQL: one key, one payment, however the requests arrive."""

import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from tests.clients.payments_api import PaymentsApi
from tests.db.checks import assert_no_rows
from tests.factories.merchant_factory import MerchantAccount
from tests.utils.allure_links import area, requirement
from tests.utils.db import Database

pytestmark = [
    pytest.mark.regression,
    pytest.mark.db,
    area("Database consistency"),
    requirement("PAY-IDEMP"),
]

KEYS = 4
REPLAYS_PER_KEY = 3


def test_no_idempotency_key_maps_to_two_payments(
    api: PaymentsApi, db: Database, merchant: MerchantAccount
) -> None:
    keys = [str(uuid4()) for _ in range(KEYS)]
    for key in keys:
        # One original request, then sequential replays of it.
        api.create(amount=700, idempotency_key=key).expect(201)
        for _ in range(REPLAYS_PER_KEY):
            api.create(amount=700, idempotency_key=key).expect(200)

    stored = db.fetch_all(
        """
        SELECT k.key, COUNT(*)::int AS key_rows, COUNT(DISTINCT k.payment_id)::int AS payments
        FROM idempotency_keys k
        WHERE k.merchant_id = %s
        GROUP BY k.key
        """,
        (merchant.id,),
    )
    assert {row["key"] for row in stored} == set(keys), "keys sent and keys stored differ"

    assert_no_rows(
        db,
        """
        SELECT k.key, COUNT(DISTINCT k.payment_id) AS payments
        FROM idempotency_keys k
        WHERE k.merchant_id = %s
        GROUP BY k.key
        HAVING COUNT(DISTINCT k.payment_id) > 1
        """,
        (merchant.id,),
        "keys that point at more than one payment",
    )
    # The other direction, the one a replay bug breaks: a payment without a key is a duplicate
    # that slipped past the lookup.
    assert_no_rows(
        db,
        """
        SELECT p.id, p.created_at
        FROM payments p
        LEFT JOIN idempotency_keys k ON k.payment_id = p.id
        WHERE p.merchant_id = %s AND k.id IS NULL
        """,
        (merchant.id,),
        "payments created without an idempotency key row",
    )
    assert db.fetch_value(
        "SELECT COUNT(*) FROM payments WHERE merchant_id = %s", (merchant.id,)
    ) == (KEYS)


def test_concurrent_requests_with_one_key_create_a_single_payment(
    api: PaymentsApi, db: Database, merchant: MerchantAccount
) -> None:
    key = str(uuid4())
    parallel = 6
    barrier = threading.Barrier(parallel)

    def post() -> int:
        barrier.wait(timeout=10)
        return api.create(amount=800, idempotency_key=key).status_code

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        statuses = list(pool.map(lambda _: post(), range(parallel)))

    assert statuses.count(201) == 1, statuses  # exactly one request created the payment
    assert set(statuses) <= {200, 201}, statuses
    rows = db.fetch_all(
        """
        SELECT k.key, COUNT(*)::int AS key_rows, COUNT(DISTINCT p.id)::int AS payments
        FROM idempotency_keys k
        JOIN payments p ON p.id = k.payment_id
        WHERE k.merchant_id = %s
        GROUP BY k.key
        """,
        (merchant.id,),
    )
    assert [(row["key"], row["key_rows"], row["payments"]) for row in rows] == [(key, 1, 1)]
    assert (
        db.fetch_value("SELECT COUNT(*) FROM payments WHERE merchant_id = %s", (merchant.id,)) == 1
    )
