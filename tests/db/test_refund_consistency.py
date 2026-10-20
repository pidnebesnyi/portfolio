"""Refund invariants checked in SQL, not through the API.

A response body can look right while the rows are wrong (the concurrency suite proved that once);
these checks read the tables directly. Every test seeds its own merchant through the API, runs a
"sanity" query that proves the data is really there, then a "violations" query that must be empty.
"""

import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.db.checks import assert_no_rows
from tests.factories.merchant_factory import MerchantAccount
from tests.factories.payment_factory import PaymentFactory
from tests.models.payments import PaymentStatus
from tests.utils.allure_links import area, requirement
from tests.utils.db import Database

pytestmark = [
    pytest.mark.regression,
    pytest.mark.db,
    area("Database consistency"),
    requirement("PAY-REFUND"),
]

# The refund sum per payment, computed from the refunds table (the source of truth).
REFUND_TOTALS = """
    SELECT p.id, p.status, p.amount, p.refunded_amount,
           COALESCE(SUM(r.amount), 0)::int AS refunds_sum,
           COUNT(r.id)::int AS refunds_count
    FROM payments p
    LEFT JOIN refunds r ON r.payment_id = p.id
    WHERE p.merchant_id = %s
    GROUP BY p.id, p.status, p.amount, p.refunded_amount
"""


@pytest.fixture
def seeded(api: PaymentsApi, payment_factory: PaymentFactory) -> dict[str, PaymentStatus]:
    """One payment per refund situation; returns {payment_id: expected final status}."""
    payments = {
        payment_factory.create(PaymentStatus.CREATED, amount=1000).id: PaymentStatus.CREATED,
        payment_factory.create(PaymentStatus.CAPTURED, amount=1000).id: PaymentStatus.CAPTURED,
        payment_factory.create(PaymentStatus.PARTIALLY_REFUNDED, amount=1000).id: (
            PaymentStatus.PARTIALLY_REFUNDED
        ),
        payment_factory.create(PaymentStatus.REFUNDED, amount=1000).id: PaymentStatus.REFUNDED,
    }
    # A payment refunded in three steps, to give the SUM something to add up.
    stepped = payment_factory.create(PaymentStatus.CAPTURED, amount=900)
    for amount in (200, 300, 400):
        api.refund(stepped.id, amount).expect(201)
    payments[stepped.id] = PaymentStatus.REFUNDED
    return {str(k): v for k, v in payments.items()}


@allure.title("Refunds never add up to more than the payment amount")
def test_refunds_never_add_up_to_more_than_the_payment_amount(
    db: Database, merchant: MerchantAccount, seeded: dict[str, PaymentStatus]
) -> None:
    totals = db.fetch_all(REFUND_TOTALS, (merchant.id,))
    assert len(totals) == len(seeded), "seeded payments are missing from the database"
    assert max(row["refunds_count"] for row in totals) == 3, "the three-step refund is missing"

    assert_no_rows(
        db,
        """
        SELECT p.id, p.amount, SUM(r.amount) AS refunds_sum
        FROM payments p
        JOIN refunds r ON r.payment_id = p.id
        WHERE p.merchant_id = %s
        GROUP BY p.id, p.amount
        HAVING SUM(r.amount) > p.amount
        """,
        (merchant.id,),
        "payments refunded for more than they were paid",
    )


@allure.title("Payment status agrees with the sum of its refunds")
def test_payment_status_agrees_with_the_sum_of_its_refunds(
    db: Database, merchant: MerchantAccount, seeded: dict[str, PaymentStatus]
) -> None:
    totals = {str(row["id"]): row for row in db.fetch_all(REFUND_TOTALS, (merchant.id,))}
    assert {pid: row["status"] for pid, row in totals.items()} == {
        pid: status.value for pid, status in seeded.items()
    }

    assert_no_rows(
        db,
        f"""
        WITH totals AS ({REFUND_TOTALS})
        SELECT id, status, amount, refunded_amount, refunds_sum
        FROM totals
        WHERE (status = 'refunded' AND refunds_sum <> amount)
           OR (status = 'partially_refunded' AND refunds_sum NOT BETWEEN 1 AND amount - 1)
           OR (status NOT IN ('refunded', 'partially_refunded') AND refunds_sum <> 0)
           OR refunded_amount <> refunds_sum
        """,
        (merchant.id,),
        "status or refunded_amount disagrees with the refunds table",
    )


@allure.title("Refund rows match the amounts the API reports")
def test_refund_rows_match_the_amounts_the_api_reports(
    api: PaymentsApi, db: Database, merchant: MerchantAccount, seeded: dict[str, PaymentStatus]
) -> None:
    """Window function: each payment's share of the merchant's total refunded money."""
    rows = db.fetch_all(
        """
        SELECT p.id, SUM(r.amount)::int AS refunded,
               ROUND(100.0 * SUM(r.amount) / SUM(SUM(r.amount)) OVER (), 1) AS share_pct
        FROM payments p
        JOIN refunds r ON r.payment_id = p.id
        WHERE p.merchant_id = %s
        GROUP BY p.id
        ORDER BY refunded DESC
        """,
        (merchant.id,),
    )

    assert len(rows) == 3  # created and plain-captured payments have no refund rows
    assert sum(row["share_pct"] for row in rows) == pytest.approx(100, abs=0.2)
    for row in rows:
        assert api.get(row["id"]).expect(200).refunded_amount == row["refunded"]
