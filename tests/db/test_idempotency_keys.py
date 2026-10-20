"""Idempotency invariants in SQL: one key, one payment."""

from uuid import uuid4

import allure
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


@allure.title("No idempotency key maps to two payments")
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

    # UNIQUE (key, merchant_id) makes this impossible today; the check guards against the
    # constraint being dropped in a later migration.
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
