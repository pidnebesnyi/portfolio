"""Tokens that look almost right, and login input at its limits."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import allure
import jwt
import pytest

from tests.clients.auth_api import AuthApi
from tests.clients.http import LoggedHttpClient
from tests.clients.payments_api import PaymentsApi
from tests.config import Settings
from tests.factories.merchant_factory import MerchantAccount
from tests.utils.allure_links import area, requirement
from tests.utils.tokens import forge_token

pytestmark = area("Authentication")


def _claims(merchant: MerchantAccount, **changes: object) -> dict[str, object]:
    return {
        "sub": str(uuid4()),
        "role": "merchant",
        "merchant_id": str(merchant.id),
        "typ": "access",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        **changes,
    }


@pytest.mark.regression
@requirement("PAY-ACCESS")
@allure.title("A token that claims no signing algorithm is rejected")
def test_unsigned_token_is_rejected(api: PaymentsApi, merchant: MerchantAccount) -> None:
    unsigned = jwt.encode(_claims(merchant), key=None, algorithm="none")

    api.with_token(unsigned).list_payments().expect_error(401, "invalid_token")


@pytest.mark.regression
@requirement("PAY-ACCESS")
@allure.title("A token without an expiry is rejected")
def test_token_without_expiry_is_rejected(
    api: PaymentsApi, merchant: MerchantAccount, settings: Settings
) -> None:
    claims = _claims(merchant)
    del claims["exp"]
    token = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")

    api.with_token(token).list_payments().expect_error(401, "invalid_token")


@pytest.mark.regression
@requirement("PAY-ACCESS")
@allure.title("A token of the wrong type is rejected")
@pytest.mark.parametrize("token_type", ["mfa", "refresh", ""])
def test_token_of_the_wrong_type_is_rejected(
    api: PaymentsApi, merchant: MerchantAccount, settings: Settings, token_type: str
) -> None:
    token = jwt.encode(_claims(merchant, typ=token_type), settings.jwt_secret, algorithm="HS256")

    api.with_token(token).list_payments().expect_error(401, "invalid_token")


@pytest.mark.regression
@requirement("PAY-ACCESS")
@allure.title("A token whose merchant id is not a UUID is rejected")
def test_token_with_a_malformed_merchant_id_is_rejected(
    api: PaymentsApi, merchant: MerchantAccount, settings: Settings
) -> None:
    token = jwt.encode(
        _claims(merchant, merchant_id="not-a-uuid"), settings.jwt_secret, algorithm="HS256"
    )

    api.with_token(token).list_payments().expect_error(401, "invalid_token")


@pytest.mark.regression
@requirement("PAY-ACCESS")
@allure.title("A well-signed token for a merchant that does not exist is rejected")
def test_token_for_a_merchant_that_does_not_exist_is_rejected(
    api: PaymentsApi, settings: Settings
) -> None:
    token = forge_token(settings.jwt_secret, user_id=uuid4(), merchant_id=uuid4())

    api.with_token(token).list_payments().expect_error(401, "invalid_token")


@pytest.mark.regression
@requirement("PAY-ACCESS")
@pytest.mark.parametrize("scheme", ["Basic abc", "Token abc", "Bearer", "abc"])
@allure.title("An Authorization header that is not a bearer token is unauthorized: {scheme}")
def test_authorization_header_that_is_not_a_bearer_token(
    http: LoggedHttpClient, scheme: str
) -> None:
    response = http.request("GET", "/payments", headers={"Authorization": scheme})

    assert response.status_code in (401, 403), response.text


@pytest.mark.regression
@requirement("AUTH-LOGIN")
@allure.title("An access token is not accepted as the second-factor token")
def test_access_token_is_not_a_second_factor_token(
    auth_api: AuthApi, merchant: MerchantAccount
) -> None:
    auth_api.two_factor(merchant.token, "123456").expect_error(401, "invalid_token")


@pytest.mark.regression
@requirement("AUTH-LOGIN")
@allure.title("An expired second-factor token is reported as expired")
def test_expired_second_factor_token_is_reported_as_expired(
    auth_api: AuthApi, settings: Settings
) -> None:
    expired = forge_token(
        settings.jwt_secret,
        user_id=uuid4(),
        role="admin",
        merchant_id=None,
        token_type="mfa",
        expires_in_s=-60,
    )

    auth_api.two_factor(expired, "123456").expect_error(401, "token_expired")


@pytest.mark.regression
@requirement("AUTH-LOGIN")
@pytest.mark.parametrize(
    ("email", "password"),
    [
        pytest.param("", "secret-password", id="empty-email"),
        pytest.param("a@lab.test", "", id="empty-password"),
        pytest.param("a@lab.test", "p" * 129, id="password-129"),
        pytest.param("e" * 250 + "@lab.test", "secret-password", id="email-257"),
    ],
)
@allure.title("Login input past its limits is a validation error: {param_id}")
def test_login_input_past_its_limits_is_a_validation_error(
    auth_api: AuthApi, email: str, password: str
) -> None:
    auth_api.login(email, password).expect_error(422, "validation_error")


@pytest.mark.regression
@requirement("AUTH-LOGIN")
@allure.title("A second-factor code longer than 16 characters is a validation error")
def test_long_second_factor_code_is_a_validation_error(
    auth_api: AuthApi, settings: Settings
) -> None:
    mfa = forge_token(
        settings.jwt_secret, user_id=uuid4(), role="admin", merchant_id=None, token_type="mfa"
    )

    auth_api.two_factor(mfa, "1" * 17).expect_error(422, "validation_error")
