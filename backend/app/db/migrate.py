"""Minimal schema upgrade for existing SQLite databases.

create_all() creates missing tables but never adds columns to tables that
already exist, so a database made by an older version would miss new
columns. This adds them, with their defaults, and renames legacy incident
statuses. It is safe to run on every start-up.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db.session import Base

LEGACY_STATUS_MAP = {"ASSIGNED": "DISPATCHED", "IN_PROGRESS": "ON_SCENE"}


def _default_sql(column) -> str:
    default = column.default.arg if column.default is not None and not callable(column.default.arg) else None
    if default is None:
        return ""
    if isinstance(default, bool):
        return f" DEFAULT {1 if default else 0}"
    if isinstance(default, (int, float)):
        return f" DEFAULT {default}"
    return " DEFAULT '" + str(default).replace("'", "''") + "'"


def upgrade_schema(engine: Engine) -> list:
    added = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                # SQLite cannot add NOT NULL columns without a default, so keep new columns nullable.
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{_default_sql(column)}'))
                added.append(f"{table.name}.{column.name}")
        if "incidents" in existing_tables:
            for old, new in LEGACY_STATUS_MAP.items():
                conn.execute(text("UPDATE incidents SET status = :new WHERE status = :old"), {"new": new, "old": old})
            # The original assessment of rows that pre-date these columns is not recoverable, so the current
            # values become the baseline from here on.
            conn.execute(text("UPDATE incidents SET reported_severity = severity WHERE reported_severity IS NULL"))
            conn.execute(text("UPDATE incidents SET reported_people_affected = people_affected WHERE reported_people_affected IS NULL"))
    return added
