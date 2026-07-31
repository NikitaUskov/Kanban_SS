"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import API_VERSION, APP_VERSION
from app.auth.router import router as auth_router
from app.boards.router import router as boards_router
from app.cards.router import router as cards_router
from app.columns.router import router as columns_router
from app.config import get_settings
from app.errors import register_exception_handlers
from app.health.router import router as health_router
from app.logging_config import configure_logging
from app.middleware import RequestContextMiddleware
from app.users.router import router as users_router

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Keep startup side effects explicit; schema changes are Alembic-only."""

    yield


app = FastAPI(
    title="Kanban Board API",
    description="Многопользовательская канбан-доска с polling-синхронизацией",
    version=APP_VERSION,
    openapi_url=f"/api/{API_VERSION}/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Server-Time"],
    max_age=600,
)
app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)

api_prefix = f"/api/{API_VERSION}"
app.include_router(health_router, prefix=api_prefix)
app.include_router(auth_router, prefix=api_prefix)
app.include_router(boards_router, prefix=api_prefix)
app.include_router(columns_router, prefix=api_prefix)
app.include_router(cards_router, prefix=api_prefix)
app.include_router(users_router, prefix=api_prefix)
