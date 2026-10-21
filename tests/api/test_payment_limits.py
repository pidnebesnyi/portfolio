"""Edges of payment input: the largest and smallest values that pass, and the first that fail."""

from typing import Any
from uuid import uuid4

import allure
import pytest

from tests.clients.payments_api import PaymentsApi
from tests.utils.allure_links import area, requirement

pytestmark = [area("Payments"), requirement("PAY-CREATE")]

MAX_AMOUNT = 100_000_000  # 1,000,000.00, the documented ceiling (app/schemas.py)


def _body(**changes: Any) -> dict[str, Any]:
    return {"amount": 100, "currency": "UAH", "description": "d", "card_token": "tok", **changes}


@pytest.mark.regression
@pytest.mark.parametrize("amount", [1, MAX_AMOUNT], ids=["smallest", "largest"])
@allure.title("The amount edge {amount} is accepted and stored as sent")
def test_amount_edges_are_accepted(api: PaymentsApi, amount: int) -> None:
    payment = api.create_raw(_body(amount=amount)).expect(201)

    assert api.get(payment.id).expect(200).amount == amount


@pytest.mark.regression
@allure.title("An amount above the ceiling is rejected")
def test_amount_above_the_ceiling_is_rejected(api: PaymentsApi) -> None:
    api.create_raw(_body(amount=MAX_AMOUNT + 1)).expect_error(422, "validation_error")


@pytest.mark.regression
@pytest.mark.parametrize(
    ("field", "value"),
    [("description", "d" * 255), ("card_token", "t" * 64), ("description", "")],
    ids=["description-255", "card-token-64", "description-empty"],
)
@allure.title("A text field at its limit is accepted: {param_id}")
def test_text_fields_at_their_limit_are_accepted(api: PaymentsApi, field: str, value: str) -> None:
    payment = api.create_raw(_body(**{field: value})).expect(201)

    assert getattr(payment, field) == value


@pytest.mark.regression
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("description", "d" * 256),
        ("card_token", "t" * 65),
        ("card_token", ""),
        ("description", "nul\x00inside"),
        ("currency", "uah"),
        ("currency", ""),
    ],
    ids=[
        "description-256",
        "card-token-65",
        "card-token-empty",
        "description-with-nul",
        "currency-lowercase",
        "currency-empty",
    ],
)
@allure.title("A text field past its limit is rejected: {param_id}")
def test_text_fields_past_their_limit_are_rejected(
    api: PaymentsApi, field: str, value: str
) -> None:
    api.create_raw(_body(**{field: value})).expect_error(422, "validation_error")


@pytest.mark.regression
@allure.title("A payment with unicode in the description is stored unchanged")
def test_unicode_description_is_stored_unchanged(api: PaymentsApi) -> None:
    text = "Оплата №42 — кава ☕ «Львів»"

    payment = api.create_raw(_body(description=text)).expect(201)

    assert api.get(payment.id).expect(200).description == text


@pytest.mark.regression
@allure.title("A payment id that is not a UUID is a validation error")
def test_payment_id_that_is_not_a_uuid_is_a_validation_error(api: PaymentsApi) -> None:
    api.get_by_raw_id("not-a-uuid").expect_error(422, "validation_error")


@pytest.mark.regression
@allure.title("A payment id nobody owns is not found")
def test_unknown_payment_id_is_not_found(api: PaymentsApi) -> None:
    api.get(uuid4()).expect_error(404, "payment_not_found")


@pytest.mark.regression
@pytest.mark.parametrize("length", [255, 256], ids=["key-255", "key-256"])
@allure.title("An idempotency key of {length} characters")
def test_idempotency_key_length_edge(api: PaymentsApi, length: int) -> None:
    response = api.create(idempotency_key="k" * length)

    if length == 255:
        response.expect(201)
    else:
        response.expect_error(400, "idempotency_key_required")
