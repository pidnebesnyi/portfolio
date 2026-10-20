from tests.clients.http import LoggedHttpClient
from tests.clients.responses import ApiResponse, parse
from tests.models.auth import LoginResponse, TokenResponse
from tests.models.base import ApiModel


class Health(ApiModel):
    status: str


class AuthApi:
    def __init__(self, http: LoggedHttpClient) -> None:
        self._http = http

    def login(self, email: str, password: str) -> ApiResponse[LoginResponse]:
        raw = self._http.request(
            "POST", "/auth/login", json_body={"email": email, "password": password}
        )
        return parse(raw, LoginResponse)

    def two_factor(self, mfa_token: str, code: str) -> ApiResponse[TokenResponse]:
        raw = self._http.request(
            "POST", "/auth/2fa", json_body={"mfa_token": mfa_token, "code": code}
        )
        return parse(raw, TokenResponse)

    def health(self) -> ApiResponse[Health]:
        return parse(self._http.request("GET", "/health"), Health)
