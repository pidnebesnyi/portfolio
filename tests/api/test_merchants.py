import secrets

import allure
import pytest

from tests.clients.auth_api import AuthApi
from tests.clients.merchants_api import MerchantsApi
from tests.factories.merchant_factory import MerchantAccount, MerchantFactory
from tests.utils.allure_links import area
from tests.utils.db import Database

VALID_PASSWORD = secrets.token_urlsafe(12)

pytestmark = area("Merchants (admin)")


@pytest.mark.regression
@allure.title("An admin creates a merchant who can log in")
def test_admin_creates_merchant_who_can_log_in(
    merchant_factory: MerchantFactory, auth_api: AuthApi
) -> None:
    account = merchant_factory.create("new")

    auth_api.login(account.email, account.password).expect(200)


@pytest.mark.regression
@allure.title("A created merchant is listed")
def test_created_merchant_is_listed(merchant: MerchantAccount, admin_api: MerchantsApi) -> None:
    # The list is capped, so under heavy parallel load a very new merchant is still on top.
    listed = admin_api.list_all(limit=500)

    assert merchant.id in {m.id for m in listed}


@pytest.mark.regression
@allure.title("A duplicate merchant email is a conflict")
def test_duplicate_merchant_email_is_a_conflict(
    merchant: MerchantAccount, admin_api: MerchantsApi
) -> None:
    admin_api.create("dup", merchant.email, merchant.password).expect_error(409, "email_taken")


@pytest.mark.regression
@pytest.mark.parametrize(
    ("name", "email", "password"),
    [
        pytest.param("", "x@lab.test", VALID_PASSWORD, id="empty-name"),
        pytest.param("n", "not-an-email", VALID_PASSWORD, id="bad-email"),
        pytest.param("n", "x@lab.test", "short", id="short-password"),
    ],
)
@allure.title("Merchant creation rejects invalid input: {param_id}")
def test_merchant_creation_validates_input(
    admin_api: MerchantsApi, name: str, email: str, password: str
) -> None:
    admin_api.create(name, email, password).expect_error(422, "validation_error")


@pytest.mark.regression
@pytest.mark.db
@allure.title("Deleting a merchant cascades and revokes access")
def test_deleting_merchant_cascades_and_revokes_access(
    merchant_factory: MerchantFactory, admin_api: MerchantsApi, auth_api: AuthApi, db: Database
) -> None:
    account = merchant_factory.create("doomed")
    payment = account.api.create().expect(201)

    admin_api.delete(account.id).expect_no_content(204)

    auth_api.login(account.email, account.password).expect_error(401, "invalid_credentials")
    account.api.get(payment.id).expect_error(401, "invalid_token")  # old token, merchant gone
    assert db.fetch_value("SELECT count(*) FROM payments WHERE id = %s", (payment.id,)) == 0
    admin_api.delete(account.id).expect_error(404, "merchant_not_found")
