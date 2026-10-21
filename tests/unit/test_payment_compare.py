from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import allure
import pytest

from tests.models.payments import PaymentStatus
from tests.utils.payment_compare import (
    diff_payments,
    norm_amount,
    norm_enum,
    norm_id,
    norm_nullable_text,
    norm_text,
    norm_timestamp,
    normalize_api,
    normalize_db,
)

pytestmark = pytest.mark.regression

ID = "3f2b8c1e-5d4a-4e6b-9a7c-1b2d3e4f5a6b"
MERCHANT = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"


def api_item(**overrides: Any) -> dict[str, Any]:
    """A payment as the JSON of GET /payments carries it."""
    item = {
        "id": ID,
        "merchant_id": MERCHANT,
        "amount": 1050,
        "currency": "UAH",
        "description": "test payment",
        "card_token": "tok_success",
        "status": "captured",
        "failure_reason": None,
        "refunded_amount": 0,
        "created_at": "2026-03-01T10:00:00.123456Z",
        "updated_at": "2026-03-01T10:00:01+00:00",
    }
    return item | overrides


def db_row(**overrides: Any) -> dict[str, Any]:
    """The same payment as psycopg returns the row, in a +02:00 session time zone."""
    zone = timezone(timedelta(hours=2))
    row = {
        "id": UUID(ID),
        "merchant_id": UUID(MERCHANT),
        "amount": 1050,
        "currency": "UAH",
        "description": "test payment",
        "card_token": "tok_success",
        "status": "captured",
        "failure_reason": None,
        "refunded_amount": 0,
        "created_at": datetime(2026, 3, 1, 12, 0, 0, 123456, tzinfo=zone),
        "updated_at": datetime(2026, 3, 1, 12, 0, 1, tzinfo=zone),
    }
    return row | overrides


@allure.title("An id compares equal as UUID, as text and in upper case")
def test_ids_compare_equal_in_any_representation() -> None:
    assert norm_id(UUID(ID)) == norm_id(ID) == norm_id(ID.upper()) == ID


@allure.title("An amount is whole minor units whether int, Decimal or text")
@pytest.mark.parametrize("value", [1050, Decimal("1050"), Decimal("1050.00"), "1050"])
def test_amount_is_an_int_whatever_it_arrives_as(value: int | Decimal | str) -> None:
    result = norm_amount(value)

    assert result == 1050
    assert type(result) is int


@allure.title("An amount with a fraction or a bool is refused, not rounded")
@pytest.mark.parametrize("value", [Decimal("10.5"), "10.50", True])
def test_amount_refuses_what_is_not_whole_minor_units(value: Any) -> None:
    with pytest.raises((ValueError, TypeError)):
        norm_amount(value)


@allure.title("A timestamp becomes UTC ISO text whatever zone or notation it came in")
def test_timestamp_is_utc_iso_text() -> None:
    expected = "2026-03-01T10:00:00.123456+00:00"

    assert norm_timestamp("2026-03-01T10:00:00.123456Z") == expected
    assert norm_timestamp("2026-03-01T12:00:00.123456+02:00") == expected
    assert norm_timestamp(datetime(2026, 3, 1, 10, 0, 0, 123456, tzinfo=UTC)) == expected
    assert norm_timestamp(datetime(2026, 3, 1, 10, 0, 0, 123456)) == expected  # naive = UTC


@allure.title("A timestamp keeps microsecond precision, also when the fraction is zero")
def test_timestamp_precision_is_the_same_for_whole_seconds() -> None:
    assert norm_timestamp("2026-03-01T10:00:01+00:00") == "2026-03-01T10:00:01.000000+00:00"
    assert norm_timestamp(datetime(2026, 3, 1, 10, 0, 1, tzinfo=UTC)) == norm_timestamp(
        "2026-03-01T10:00:01Z"
    )


@allure.title("An enum member and its text value normalize to the same text")
def test_enum_and_text_normalize_alike() -> None:
    assert norm_enum(PaymentStatus.CAPTURED) == norm_enum("captured") == "captured"


@allure.title("A nullable text reads as None when NULL, missing or empty")
def test_nullable_text_collapses_null_missing_and_empty() -> None:
    assert norm_nullable_text(None) == norm_nullable_text("") is None
    assert norm_nullable_text("card declined") == "card declined"
    without_key = api_item()
    del without_key["failure_reason"]
    assert normalize_api([without_key], 1) == normalize_api([api_item(failure_reason="")], 1)


@allure.title("A NOT NULL text reads as an empty string when NULL, missing or empty")
def test_required_text_collapses_null_missing_and_empty() -> None:
    assert norm_text(None) == norm_text("") == ""
    without_key = api_item()
    del without_key["description"]
    assert normalize_api([without_key], 1) == normalize_api([api_item(description=None)], 1)


@allure.title("The same payment in API and database notation gives an empty diff")
def test_same_payment_in_both_notations_has_no_diff() -> None:
    assert not diff_payments(normalize_api([api_item()], 1), normalize_db([db_row()]))


@allure.title("The order of the payments does not matter")
def test_order_is_ignored() -> None:
    other_id = "9c8b7a6f-5e4d-4c3b-8a29-1f0e9d8c7b6a"
    api = [api_item(), api_item(id=other_id, amount=500)]
    rows = [db_row(id=UUID(other_id), amount=500), db_row()]

    assert not diff_payments(normalize_api(api, 2), normalize_db(rows))


@allure.title("A different amount shows up in the diff, naming the field")
def test_changed_amount_shows_in_the_diff() -> None:
    diff = diff_payments(normalize_api([api_item(amount=1051)], 1), normalize_db([db_row()]))

    assert diff
    assert "amount" in diff.pretty()
    assert "1051" in diff.pretty()


@allure.title("A different status shows up in the diff")
def test_changed_status_shows_in_the_diff() -> None:
    diff = diff_payments(normalize_api([api_item(status="refunded")], 1), normalize_db([db_row()]))

    assert "status" in diff.pretty()


@allure.title("A timestamp one microsecond apart shows up in the diff")
def test_timestamp_off_by_a_microsecond_shows_in_the_diff() -> None:
    api = api_item(created_at="2026-03-01T10:00:00.123457Z")

    assert diff_payments(normalize_api([api], 1), normalize_db([db_row()]))


@allure.title("A payment missing on either side and a wrong total show up in the diff")
def test_missing_payment_and_wrong_total_show_in_the_diff() -> None:
    other_id = "9c8b7a6f-5e4d-4c3b-8a29-1f0e9d8c7b6a"
    api_only = diff_payments(normalize_api([api_item()], 1), normalize_db([]))
    db_only = diff_payments(
        normalize_api([], 0), normalize_db([db_row(), db_row(id=UUID(other_id))])
    )
    total_only = diff_payments(normalize_api([api_item()], 5), normalize_db([db_row()]))

    assert api_only
    assert db_only
    assert "total" in total_only.pretty()
