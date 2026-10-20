from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import ApiError

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str


@router.get("/health", response_model=Health, responses={503: {"description": "Database down"}})
def health(session: Session = Depends(get_session)) -> Health:
    """200 only when the database answers."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise ApiError(503, "db_unavailable", "Database is not reachable") from None
    return Health(status="ok")
