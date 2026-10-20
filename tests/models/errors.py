from pydantic import BaseModel, ConfigDict, Field


class ErrorBody(BaseModel):
    """Error payload. Extra keys vary by code (`from`/`action`, `refundable`, `errors`)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    code: str
    message: str | None = None
    from_status: str | None = Field(default=None, alias="from")
    action: str | None = None
    refundable: int | None = None
