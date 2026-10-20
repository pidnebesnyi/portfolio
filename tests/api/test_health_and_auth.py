import allure
import pytest

from tests.clients.auth_api import AuthApi
from tests.clients.http import LoggedHttpClient
from tests.clients.merchants_api import MerchantsApi
from tests.config import Settings
from tests.factories.merchant_factory import MerchantAccount
from tests.utils.allure_links import area, requirement
from tests.utils.tokens import decode_unverified, totp_code

pytestmark = area("Authentication")


@pytest.mark.regression
@requirement("OBS-HEALTH")
@allure.title("Health reports ok when the database is up")
def test_health_reports_ok_when_database_is_up(auth_api: AuthApi) -> None:
    assert auth_api.health().expect(200).status == "ok"


@pytest.mark.regression
@requirement("AUTH-LOGIN")
@allure.title("Merchant login returns a token with the expected claims")
def test_merchant_login_returns_token_with_expected_claims(
    auth_api: AuthApi, merchant: MerchantAccount
) -> None:
    login = auth_api.login(merchant.email, merchant.password).expect(200)

    assert login.token_type == "bearer"
    assert login.mfa_required is None  # merchants skip 2FA
    assert login.access_token
    claims = decode_unverified(login.access_token)
    assert claims["role"] == "merchant"
    assert claims["merchant_id"] == str(merchant.id)
    assert {"sub", "exp"} <= claims.keys()


@pytest.mark.regression
@requirement("AUTH-LOGIN")
@allure.title("Login with a wrong password is rejected")
def test_login_with_wrong_password_is_rejected(
    auth_api: AuthApi, merchant: MerchantAccount
) -> None:
    auth_api.login(merchant.email, "not-" + merchant.password).expect_error(
        401, "invalid_credentials"
    )


@pytest.mark.regression
@requirement("AUTH-LOGIN")
@allure.title("Login with an unknown email is rejected")
def test_login_with_unknown_email_is_rejected(auth_api: AuthApi) -> None:
    auth_api.login("nobody@lab.test", "irrelevant-password").expect_error(
        401, "invalid_credentials"
    )


@pytest.mark.regression
@requirement("AUTH-LOGIN")
@allure.title("Admin login requires a second factor")
def test_admin_login_requires_second_factor(auth_api: AuthApi, settings: Settings) -> None:
    step_one = auth_api.login(settings.admin_email, settings.admin_password).expect(200)

    assert step_one.mfa_required is True
    assert step_one.access_token is None, "password alone must not yield an access token"
    assert step_one.mfa_token

    token = auth_api.two_factor(step_one.mfa_token, totp_code(settings.admin_totp_secret)).expect(
        200
    )
    claims = decode_unverified(token.access_token)
    assert claims["role"] == "admin"
    assert claims["merchant_id"] is None


@pytest.mark.regression
@requirement("AUTH-LOGIN")
@allure.title("A wrong second-factor code is rejected")
def test_wrong_second_factor_code_is_rejected(auth_api: AuthApi, settings: Settings) -> None:
    step_one = auth_api.login(settings.admin_email, settings.admin_password).expect(200)
    assert step_one.mfa_token
    valid = totp_code(settings.admin_totp_secret)
    wrong = "000000" if valid != "000000" else "111111"

    auth_api.two_factor(step_one.mfa_token, wrong).expect_error(401, "invalid_code")


@pytest.mark.regression
@requirement("AUTH-LOGIN")
@allure.title("A second-factor token cannot be used as an access token")
def test_mfa_token_cannot_be_used_as_access_token(
    auth_api: AuthApi, http: LoggedHttpClient, settings: Settings
) -> None:
    step_one = auth_api.login(settings.admin_email, settings.admin_password).expect(200)
    assert step_one.mfa_token

    MerchantsApi(http, step_one.mfa_token).list_raw().expect_error(401, "invalid_token")
