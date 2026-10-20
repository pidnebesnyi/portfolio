from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import request_log
from app.bootstrap import ensure_admin
from app.config import get_settings
from app.errors import install_error_handlers
from app.routers import auth, health, merchants, payments, ui


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()  # fail fast with a clear error when required variables are missing
    request_log.configure(settings.log_file)
    ensure_admin()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Payments Lab API",
    version="0.1.0",
    description="Object under test for payments-qa-lab. Amounts are integers in minor units.",
)
install_error_handlers(app)
app.add_middleware(request_log.RequestLogMiddleware)
for module in (health, auth, merchants, payments, ui):
    app.include_router(module.router)
