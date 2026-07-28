"""UTC and UUID helpers shared by domain modules."""

from datetime import UTC, datetime
from uuid import uuid4


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def new_uuid() -> str:
    """Return a lowercase UUID string for external identifiers."""

    return str(uuid4())


def isoformat_z(value: datetime) -> str:
    """Serialize a UTC datetime with an explicit Z suffix."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def as_utc(value: datetime) -> datetime:
    """Normalize SQLite's possibly naive datetime back to aware UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

