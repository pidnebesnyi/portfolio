from tests.models.base import ApiModel


class LoginResponse(ApiModel):
    access_token: str | None = None
    token_type: str | None = None
    mfa_required: bool | None = None
    mfa_token: str | None = None


class TokenResponse(ApiModel):
    access_token: str
    token_type: str
