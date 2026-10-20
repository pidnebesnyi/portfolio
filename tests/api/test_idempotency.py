from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from tests.clients.payments_api import PaymentsApi
from tests.factories.merchant_factory import MerchantAccount
from tests.utils.allure_links import area, requirement
from tests.utils.db import Database

pytestmark = [area("Idempotency"), requirement("PAY-IDEMP")]

REPLAY_HEADER = "Idempotent-Replayed"


@pytest.mark.smoke
def test_same_key_and_body_returns_the_same_payment(api: PaymentsApi) -> None:
    key = str(uuid4())

    first = api.create(amount=500, idempotency_key=key)
    second = api.create(amount=500, idempotency_key=key)

    created = first.expect(201)
    replayed = second.expect(200)
    assert replayed == created
    assert REPLAY_HEADER not in first.headers
    assert second.headers[REPLAY_HEADER] == "true"


@pytest.mark.smoke
def test_same_key_with_different_body_is_a_conflict(api: PaymentsApi) -> None:
    key = str(uuid4())
    api.create(amount=500, idempotency_key=key).expect(201)

    api.create(amount=501, idempotency_key=key).expect_error(409, "idempotency_key_reused")


@pytest.mark.smoke
def test_missing_idempotency_key_is_rejected(api: PaymentsApi) -> None:
    api.create(idempotency_key=None).expect_error(400, "idempotency_key_required")


@pytest.mark.regression
@pytest.mark.parametrize(
    ("field", "value"),
    [("currency", "USD"), ("description", "other"), ("card_token", "tok_other")],
)
def test_any_changed_field_counts_as_a_different_body(
    api: PaymentsApi, field: str, value: str
) -> None:
    key = str(uuid4())
    base = {"amount": 700, "currency": "UAH", "description": "d", "card_token": "tok_success"}
    api.create_raw(base, idempotency_key=key).expect(201)

    api.create_raw({**base, field: value}, idempotency_key=key).expect_error(
        409, "idempotency_key_reused"
    )


@pytest.mark.regression
def test_replay_does_not_depend_on_payment_progress(api: PaymentsApi) -> None:
    key = str(uuid4())
    created = api.create(idempotency_key=key).expect(201)
    api.authorize(created.id).expect(200)

    replayed = api.create(idempotency_key=key).expect(200)

    assert replayed.id == created.id
    assert replayed.status.value == "authorized", "a replay returns the current state"


@pytest.mark.regression
def test_keys_are_scoped_per_merchant(api: PaymentsApi, other_merchant: MerchantAccount) -> None:
    key = str(uuid4())

    mine = api.create(idempotency_key=key).expect(201)
    theirs = other_merchant.api.create(idempotency_key=key).expect(201)

    assert mine.id != theirs.id


@pytest.mark.regression
@pytest.mark.db
def test_replay_creates_no_second_row(
    api: PaymentsApi, merchant: MerchantAccount, db: Database
) -> None:
    key = str(uuid4())
    for _ in range(3):
        api.create(idempotency_key=key)

    payments = db.fetch_value(
        "SELECT count(*) FROM payments WHERE merchant_id = %s", (merchant.id,)
    )
    keys = db.fetch_value(
        "SELECT count(*) FROM idempotency_keys WHERE merchant_id = %s AND key = %s",
        (merchant.id, key),
    )
    assert (payments, keys) == (1, 1)


@pytest.mark.regression
@pytest.mark.db
def test_parallel_requests_with_one_key_create_one_payment(
    api: PaymentsApi, merchant: MerchantAccount, db: Database
) -> None:
    key = str(uuid4())
    workers = 5

    with ThreadPoolExecutor(max_workers=workers) as pool:
        responses = list(pool.map(lambda _: api.create(idempotency_key=key), range(workers)))

    assert sorted(r.status_code for r in responses) == [200] * (workers - 1) + [201]
    assert len({r.expect(r.status_code).id for r in responses}) == 1
    count = db.fetch_value("SELECT count(*) FROM payments WHERE merchant_id = %s", (merchant.id,))
    assert count == 1
