from tests.models.base import ApiModel


class ChargeRecord(ApiModel):
    """One charge as the provider mock received it (GET /__requests)."""

    amount: int
    currency: str
    card_token: str
    reference: str | None
