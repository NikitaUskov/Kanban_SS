"""Alembic runtime configured from the same .env as the application."""

from logging.config import fileConfig

from alembic import context

from app import models  # noqa: F401
from app.config import get_settings
from app.database import Base, engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        sqlite_connection = None
        if connection.dialect.name == "sqlite":
            # SQLite cannot recreate a referenced table while foreign-key checks
            # are enabled. Alembic batch migrations recreate tables, so disable
            # checks on the raw DB-API connection before the migration starts.
            sqlite_connection = connection.connection.dbapi_connection
            sqlite_connection.execute("PRAGMA foreign_keys=OFF")
        try:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            if sqlite_connection is not None:
                violations = sqlite_connection.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise RuntimeError(
                        "После миграции обнаружены нарушения внешних ключей: "
                        f"{violations[:10]}"
                    )
        finally:
            if sqlite_connection is not None:
                sqlite_connection.execute("PRAGMA foreign_keys=ON")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
