from datetime import datetime
from uuid import UUID

from tests.models.base import ApiModel


class Merchant(ApiModel):
    id: UUID
    name: str
    email: str
    created_at: datetime
