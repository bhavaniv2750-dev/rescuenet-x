"""Alembic environment. The URL comes from cfg.attributes['url'] when set (tests, the startup helper),
otherwise from app settings."""
from alembic import context
from sqlalchemy import create_engine

from app.core.config import settings
from app.db.session import Base
import app.models.entities  # noqa: F401  (registers every table on Base.metadata)

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.attributes.get("url") or settings.DATABASE_URL


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(_url(), connect_args={"check_same_thread": False} if _url().startswith("sqlite") else {})
    with engine.connect() as conn:
        _run(conn)
    engine.dispose()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=connection.dialect.name == "sqlite", compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) mode is not supported; run migrations against a database.")
run_migrations_online()
