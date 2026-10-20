"""Aggregates over a merchant's payments must equal what the API reports, and deleting a merchant
must leave nothing of theirs behind."""

import pytest

from tests.clients.merchants_api import MerchantsApi
from tests.clients.payments_api import PaymentsApi
from tests.db.checks import assert_no_rows
from tests.factories.merchant_factory import MerchantAccount, MerchantFactory
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.allure_links import area, requirement
from tests.utils.db import Database

pytestmark = [pytest.mark.regression, pytest.mark.db, area("Database consistency")]

# status -> how many payments to create (amount = 1000 + 100 * position, to make sums distinct)
MIX = {
    PaymentStatus.CREATED: 2,
    PaymentStatus.AUTHORIZED: 1,
    PaymentStatus.VOIDED: 1,
    PaymentStatus.CAPTURED: 3,
    PaymentStatus.PARTIALLY_REFUNDED: 2,
    PaymentStatus.REFUNDED: 1,
}


@requirement("PAY-LIST")
def test_totals_per_status_equal_what_the_api_lists(
    api: PaymentsApi, db: Database, merchant: MerchantAccount, payment_factory: PaymentFactory
) -> None:
    position = 0
    for status, count in MIX.items():
        for _ in range(count):
            payment_factory.create(status, amount=1000 + 100 * position)
            position += 1

    rows = db.fetch_all(
        """
        SELECT status,
               COUNT(*)::int AS payments,
               SUM(amount)::int AS amount_sum,
               SUM(refunded_amount)::int AS refunded_sum,
               SUM(COUNT(*)) OVER ()::int AS all_payments
        FROM payments
        WHERE merchant_id = %s
        GROUP BY status
        ORDER BY status
        """,
        (merchant.id,),
    )

    assert {row["status"]: row["payments"] for row in rows} == {
        status.value: count for status, count in MIX.items()
    }
    everything = api.list_payments(limit=100).expect(200)
    assert everything.total == rows[0]["all_payments"] == sum(MIX.values())
    for row in rows:
        listed = api.list_payments(status=PaymentStatus(row["status"]), limit=100).expect(200)
        assert listed.total == row["payments"], row["status"]
        assert sum(p.amount for p in listed.items) == row["amount_sum"], row["status"]
        assert sum(p.refunded_amount for p in listed.items) == row["refunded_sum"], row["status"]


@requirement("MERCH-DELETE")
def test_deleting_a_merchant_leaves_no_payments_refunds_or_keys(
    merchant_factory: MerchantFactory, admin_api: MerchantsApi, db: Database
) -> None:
    doomed = merchant_factory.create("doomed")
    payment = doomed.api.create(amount=1000).expect(201)
    doomed.api.authorize(payment.id).expect(200)
    doomed.api.capture(payment.id).expect(200)
    doomed.api.refund(payment.id, 400).expect(201)
    leftovers = """
        SELECT 'payments' AS tbl, COUNT(*)::int AS n FROM payments WHERE merchant_id = %(m)s
        UNION ALL
        SELECT 'refunds', COUNT(*)::int FROM refunds r
            JOIN payments p ON p.id = r.payment_id WHERE p.merchant_id = %(m)s
        UNION ALL
        SELECT 'idempotency_keys', COUNT(*)::int FROM idempotency_keys WHERE merchant_id = %(m)s
        UNION ALL
        SELECT 'users', COUNT(*)::int FROM users WHERE merchant_id = %(m)s
    """
    before = {row["tbl"]: row["n"] for row in db.fetch_all(leftovers, {"m": doomed.id})}
    assert before == {"payments": 1, "refunds": 1, "idempotency_keys": 1, "users": 1}

    admin_api.delete(doomed.id).expect_no_content(204)

    assert_no_rows(
        db,
        f"SELECT * FROM ({leftovers}) t WHERE n > 0",
        {"m": doomed.id},
        "rows left behind by a deleted merchant",
    )
