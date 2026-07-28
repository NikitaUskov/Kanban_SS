"""Database liveness and migration readiness checks."""

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app import EXPECTED_ALEMBIC_REVISION
from app.config import get_settings
from app.database import engine
from app.errors import AppError
from app.health.schemas import HealthResponse, ReadyResponse
from app.timeutils import utcnow

REQUIRED_TABLES = {
    "users",
    "refresh_tokens",
    "boards",
    "columns",
    "cards",
    "activity_log",
    "alembic_version",
}


def health() -> HealthResponse:
    settings = get_settings()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError as exc:
        raise AppError(
            503,
            "DATABASE_UNAVAILABLE",
            "База данных временно недоступна",
        ) from exc
    return HealthResponse(
        status="ok",
        app_version=settings.app_version,
        api_version=settings.api_version,
        database="ok",
        time=utcnow(),
    )


def ready() -> ReadyResponse:
    base = health()
    try:
        table_names = set(inspect(engine).get_table_names())
        missing = sorted(REQUIRED_TABLES - table_names)
        if missing:
            raise AppError(
                503,
                "DATABASE_SCHEMA_INCOMPLETE",
                "Не применены миграции базы данных",
                {"missingTables": missing},
            )
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
        if revision != EXPECTED_ALEMBIC_REVISION:
            raise AppError(
                503,
                "DATABASE_MIGRATION_OUTDATED",
                "Версия схемы базы данных не соответствует приложению",
                {
                    "currentRevision": revision,
                    "expectedRevision": EXPECTED_ALEMBIC_REVISION,
                },
            )
    except AppError:
        raise
    except SQLAlchemyError as exc:
        raise AppError(503, "DATABASE_NOT_READY", "База данных не готова к работе") from exc
    return ReadyResponse(
        **base.model_dump(),
        alembic_revision=EXPECTED_ALEMBIC_REVISION,
        required_tables=sorted(REQUIRED_TABLES),
    )

