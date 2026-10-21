"""Put a payment as the API lists it and as the database stores it into one plain shape, so a
single DeepDiff call can compare the two (tests/db/test_api_matches_db.py).

Every rule is one small function and applies to both sides, so a difference that survives
normalization is a real one:

- ids: UUID or text, any letter case -> lower-case canonical text.
- amounts: int, Decimal (SQL aggregates, numeric columns) or numeric text -> int minor units.
- timestamps: datetime (psycopg, session time zone) or ISO 8601 text (JSON, "Z" or an offset)
  -> UTC ISO text at microsecond precision, the finest both sides can hold.
- enums vs text: a StrEnum member and its value -> the plain value.
- NULL vs missing vs empty: a nullable text column (failure_reason) -> None for all three;
  a NOT NULL text column with an empty default (description) -> "" for all three.

Not compared on purpose:
- The list envelope's `limit` and `offset` describe the paging the test chose, not a payment.
  The envelope's `total` is compared, against the number of rows SQL returns.
- The database has no payment column the API leaves out; `payments` is read column by column
  (not SELECT *), so a column added to the table later is a visible decision, not a silent one.
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from deepdiff import DeepDiff

# One name per payments column, in the order both normalizers emit them.
PAYMENT_COLUMNS = (
    "id",
    "merchant_id",
    "amount",
    "currency",
    "description",
    "card_token",
    "status",
    "failure_reason",
    "refunded_amount",
    "created_at",
    "updated_at",
)


def norm_id(value: UUID | str) -> str:
    return str(UUID(str(value)))


def norm_amount(value: int | Decimal | str) -> int:
    """Minor units as int. Anything with a fractional part is refused, not rounded."""
    if isinstance(value, bool):
        raise TypeError("a bool is not an amount")
    number = Decimal(str(value))
    if number != number.to_integral_value():
        raise ValueError(f"amount {value!r} is not a whole number of minor units")
    return int(number)


def norm_timestamp(value: datetime | str) -> str:
    """UTC ISO text with microseconds. A value without a zone is taken as already UTC."""
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def norm_enum(value: Enum | str) -> str:
    return str(value.value if isinstance(value, Enum) else value)


def norm_nullable_text(value: str | None) -> str | None:
    return value or None


def norm_text(value: str | None) -> str:
    return value or ""


def _normalize(record: dict[str, Any]) -> dict[str, Any]:
    # .get() for the two text fields that may be NULL or absent; the rest must be there
    return {
        "id": norm_id(record["id"]),
        "merchant_id": norm_id(record["merchant_id"]),
        "amount": norm_amount(record["amount"]),
        "currency": norm_enum(record["currency"]),
        "description": norm_text(record.get("description")),
        "card_token": record["card_token"],
        "status": norm_enum(record["status"]),
        "failure_reason": norm_nullable_text(record.get("failure_reason")),
        "refunded_amount": norm_amount(record["refunded_amount"]),
        "created_at": norm_timestamp(record["created_at"]),
        "updated_at": norm_timestamp(record["updated_at"]),
    }


def normalize_api(items: list[dict[str, Any]], total: int) -> dict[str, Any]:
    """The JSON of every page of GET /payments, concatenated, plus the envelope's `total`."""
    return {"total": total, "payments": [_normalize(item) for item in items]}


def normalize_db(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The rows of `SELECT <PAYMENT_COLUMNS> FROM payments`; the total is simply their count."""
    return {"total": len(rows), "payments": [_normalize(row) for row in rows]}


def diff_payments(api_side: dict[str, Any], db_side: dict[str, Any]) -> DeepDiff:
    """The one comparison. The database is the reference (t1), so 'added' means the API lists
    something SQL does not hold and 'removed' means the API leaves out something SQL holds.
    Order is ignored: the API sorts newest first, the query does not sort at all. Level 2 prints
    the whole record of an added or removed payment instead of just its position."""
    return DeepDiff(db_side, api_side, ignore_order=True, report_repetition=True, verbose_level=2)
