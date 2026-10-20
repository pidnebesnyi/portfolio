from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base for response models. `forbid` makes an unexpected field (say, a leaked
    password_hash) fail the call that returned it instead of passing unnoticed."""

    model_config = ConfigDict(extra="forbid")
