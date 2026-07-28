"""Portable SQLAlchemy types used by SQLite now and PostgreSQL later."""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Persist UTC and always return timezone-aware UTC values."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DateTime(timezone=dialect.name != "sqlite"))

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Datetime value must include timezone information")
        normalized = value.astimezone(UTC)
        return normalized.replace(tzinfo=None) if dialect.name == "sqlite" else normalized

    def process_result_value(self, value: datetime | None, _dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
