"""Merchant input at its limits, and deleting what is already gone."""

import secrets
from collections.abc import Iterator
from uuid import UUID, uuid4

import allure
import pytest

from tests.clients.auth_api import AuthApi
from tests.clients.merchants_api import MerchantsApi
from tests.utils.allure_links import area, requirement

pytestmark = area("Merchants (admin)")


@pytest.fixture
def cleanup(admin_api: MerchantsApi) -> Iterator[list[UUID]]:
    """Merchants created on purpose by a test, deleted afterwards (the factory makes its own)."""
    created: list[UUID] = []
    yield created
    for merchant_id in created:
        admin_api.delete(merchant_id)


def _unique_email() -> str:
    return f"edge-{uuid4().hex[:12]}@lab.test"


@pytest.mark.regression
@requirement("MERCH-CREATE")
@pytest.mark.parametrize(
    ("name_length", "password_length"),
    [(1, 8), (100, 72)],
    ids=["shortest", "longest"],
)
@allure.title("A merchant with the {param_id} allowed name and password can log in")
def test_merchant_at_the_limits_can_log_in(
    admin_api: MerchantsApi,
    auth_api: AuthApi,
    cleanup: list[UUID],
    name_length: int,
    password_length: int,
) -> None:
    email = _unique_email()
    password = secrets.token_urlsafe(80)[:password_length]

    merchant = admin_api.create("n" * name_length, email, password).expect(201)
    cleanup.append(merchant.id)

    auth_api.login(email, password).expect(200)


@pytest.mark.regression
@requirement("MERCH-CREATE")
@pytest.mark.parametrize(
    ("name", "email", "password"),
    [
        pytest.param("n" * 101, "{email}", "long-enough-pw", id="name-101"),
        pytest.param("n", "{email}", "p" * 73, id="password-73"),
        pytest.param("n", "has space@lab.test", "long-enough-pw", id="email-with-space"),
        pytest.param("n", "two@@lab.test", "long-enough-pw", id="email-with-two-at-signs"),
        pytest.param("n", "@lab.test", "long-enough-pw", id="email-without-local-part"),
    ],
)
@allure.title("Merchant input past its limits is rejected: {param_id}")
def test_merchant_input_past_its_limits_is_rejected(
    admin_api: MerchantsApi, cleanup: list[UUID], name: str, email: str, password: str
) -> None:
    response = admin_api.create(name, email.format(email=_unique_email()), password)
    if response.status_code == 201:
        cleanup.append(response.expect(201).id)

    response.expect_error(422, "validation_error")


@pytest.mark.regression
@requirement("MERCH-CREATE")
@pytest.mark.parametrize("limit", [0, 501, -1])
@allure.title("The merchant list rejects a page size of {limit}")
def test_merchant_list_rejects_a_bad_page_size(admin_api: MerchantsApi, limit: int) -> None:
    admin_api.list_raw({"limit": limit}).expect_error(422, "validation_error")


@pytest.mark.regression
@requirement("MERCH-DELETE")
@allure.title("Deleting a merchant that is already gone is not found")
def test_deleting_a_merchant_twice_is_not_found(
    admin_api: MerchantsApi, cleanup: list[UUID]
) -> None:
    merchant = admin_api.create("gone", _unique_email(), secrets.token_urlsafe(12)).expect(201)
    cleanup.append(merchant.id)
    admin_api.delete(merchant.id).expect_no_content()

    admin_api.delete(merchant.id).expect_error(404, "merchant_not_found")


@pytest.mark.regression
@requirement("MERCH-DELETE")
@allure.title("Deleting a merchant that never existed is not found")
def test_deleting_an_unknown_merchant_is_not_found(admin_api: MerchantsApi) -> None:
    admin_api.delete(uuid4()).expect_error(404, "merchant_not_found")
