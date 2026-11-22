"""Schema management with Alembic.

ensure_schema() is what the app calls at start-up:

* empty database                      -> create everything with the migrations ("upgrade head")
* database already managed by Alembic -> back it up first when changes are pending, then upgrade
* older database without Alembic      -> back it up, bring it up to the baseline shape with the legacy
                                         helper, check nothing is missing, stamp the baseline, then upgrade

A backup is always taken before an existing database is changed. If it cannot be taken, nothing is changed.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.autogenerate import compare_metadata
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.db import backup as backup_mod
from app.db.migrate import upgrade_schema
from app.db.session import Base
import app.models.entities  # noqa: F401  (registers every table on Base.metadata; required by every function here)

BASELINE_REVISION = "0001"
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class MigrationError(RuntimeError):
    pass


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["url"] = url or settings.DATABASE_URL
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def schema_drift(engine: Engine) -> list:
    """Differences between the live schema and the models (missing/extra tables and columns, types)."""
    with engine.connect() as conn:
        return compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)


def _missing_structure(engine: Engine) -> list:
    """Tables or columns the models have but the database lacks (the only drift that blocks stamping)."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = []
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            missing.append(table.name)
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        missing += [f"{table.name}.{c.name}" for c in table.columns if c.name not in have]
    return missing


def _create_missing_indexes(engine: Engine) -> list:
    """create_all() adds no indexes to tables that already exist, so an older database lacks the newer ones."""
    inspector = inspect(engine)
    made = []
    for table in Base.metadata.sorted_tables:
        have = {i["name"] for i in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name not in have:
                index.create(bind=engine)
                made.append(index.name)
    return made


def _run(engine: Engine, fn) -> None:
    cfg = alembic_config(str(engine.url.render_as_string(hide_password=False)))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        fn(cfg)


def upgrade(engine: Engine, revision: str = "head") -> None:
    _run(engine, lambda cfg: command.upgrade(cfg, revision))


def downgrade(engine: Engine, revision: str) -> None:
    _run(engine, lambda cfg: command.downgrade(cfg, revision))


def stamp(engine: Engine, revision: str) -> None:
    _run(engine, lambda cfg: command.stamp(cfg, revision))


def _backup_before_change(engine: Engine, label: str) -> Path | None:
    if engine.dialect.name != "sqlite":
        print(f"[migrations] Not a SQLite database; take your own backup before this change ({label}).")
        return None
    try:
        path = backup_mod.sqlite_path_from_url(str(engine.url))
        target = backup_mod.create_backup(path, settings.BACKUP_DIR, label)
        backup_mod.verify_backup(target)
    except backup_mod.BackupError as exc:
        raise MigrationError(f"Could not back up the database, so it was NOT changed: {exc}") from exc
    print(f"[migrations] Verified backup written before migration: {target.name}")
    return target


def ensure_schema(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    app_tables = tables - {"alembic_version"}

    if "alembic_version" in tables:
        if current_revision(engine) != head_revision():
            _backup_before_change(engine, "pre-migration")
            upgrade(engine)
            print(f"[migrations] Upgraded to {head_revision()}")
        # Models may not add columns by hand any more, but keep older fix-ups (status renames, backfills) running.
        upgrade_schema(engine)
        return

    if not app_tables:
        upgrade(engine)
        upgrade_schema(engine)  # no-op on a fresh schema; keeps backfill statements identical on every path
        print(f"[migrations] New database created at revision {head_revision()}")
        return

    # Existing database from before Alembic.
    _backup_before_change(engine, "pre-baseline")
    Base.metadata.create_all(bind=engine)   # tables added by newer code
    added = upgrade_schema(engine)          # columns added by newer code, legacy status renames, backfills
    if added:
        print(f"[migrations] Added missing columns: {', '.join(added)}")
    made = _create_missing_indexes(engine)
    if made:
        print(f"[migrations] Created missing indexes: {', '.join(made)}")
    missing = _missing_structure(engine)
    if missing:
        raise MigrationError(f"Existing database still lacks {', '.join(missing)}; not stamping it. "
                             "Restore the pre-baseline backup and report this.")
    stamp(engine, BASELINE_REVISION)
    if current_revision(engine) != head_revision():
        upgrade(engine)
    print(f"[migrations] Existing database adopted by Alembic at {BASELINE_REVISION}; now at {head_revision()}")
