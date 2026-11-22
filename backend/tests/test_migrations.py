"""M0: Alembic baseline, adoption of older databases, up/down/up, and backups before any change."""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.db import backup as backup_mod
from app.db import migrations
from app.db.session import Base
import app.models.entities  # noqa: F401

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_DIR", tmp_path / "backups")
    eng = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    yield eng
    eng.dispose()


def _tables(eng):
    return set(inspect(eng).get_table_names()) - {"alembic_version"}


def _columns(eng):
    insp = inspect(eng)
    return {t: sorted(c["name"] for c in insp.get_columns(t)) for t in _tables(eng)}


def _model_columns():
    return {t.name: sorted(c.name for c in t.columns) for t in Base.metadata.sorted_tables}


def test_fresh_database_matches_models_exactly(engine):
    migrations.ensure_schema(engine)
    assert migrations.current_revision(engine) == migrations.head_revision()
    assert _columns(engine) == _model_columns()
    assert migrations.schema_drift(engine) == []


def test_models_and_migrations_cannot_drift_apart(engine):
    """Fails if a model changes without a migration (or the reverse)."""
    migrations.upgrade(engine)
    assert migrations.schema_drift(engine) == []


def test_up_down_up_is_clean(engine):
    migrations.upgrade(engine)
    first = _columns(engine)
    migrations.downgrade(engine, "base")
    assert _tables(engine) == set()
    migrations.upgrade(engine)
    assert _columns(engine) == first
    assert migrations.schema_drift(engine) == []


def _make_legacy_db(engine):
    """A database as an older version of the app left it: no Alembic, a missing table, missing columns."""
    migrations.baseline_metadata().create_all(bind=engine)   # the 0001 shape, no Alembic bookkeeping
    with engine.begin() as c:
        c.execute(text("DROP TABLE audit_logs"))
        c.execute(text("DROP INDEX ix_incidents_beacon_id"))
        for col in ("reported_severity", "reported_people_affected", "risk_downgraded_by", "risk_downgrade_note"):
            c.execute(text(f"ALTER TABLE incidents DROP COLUMN {col}"))
        c.execute(text("INSERT INTO incidents (id,title,description,area,latitude,longitude,severity,people_affected,"
                       "status,source,data_label,created_at,updated_at) VALUES ('INC-LEG','t','d','a',12.9,77.6,'HIGH',7,'ASSIGNED',"
                       "'CITIZEN_REPORT','SIMULATED','2025-01-01','2025-01-01')"))
        c.execute(text("INSERT INTO volunteers (id,name,phone,email,skills,area,is_verified,status,registered_at) "
                       "VALUES ('V-LEG','n','1','e@example.org','s','a',0,'AVAILABLE','2025-01-01')"))


def test_legacy_database_is_backed_up_adopted_and_keeps_its_data(engine):
    _make_legacy_db(engine)
    assert migrations.current_revision(engine) is None

    migrations.ensure_schema(engine)

    # a verified backup exists and holds the ORIGINAL rows
    backups = sorted(settings.BACKUP_DIR.glob("*.db.bak"))
    assert len(backups) == 1 and "pre-baseline" in backups[0].name
    manifest = backup_mod.verify_backup(backups[0])
    assert manifest["table_row_counts"]["incidents"] == 1 and manifest["table_row_counts"]["volunteers"] == 1
    old = sqlite3.connect(backups[0]).execute("SELECT status FROM incidents").fetchone()[0]
    assert old == "ASSIGNED"  # the backup is untouched by the legacy status rename

    # live database adopted, schema complete, data preserved and fixed up
    assert migrations.current_revision(engine) == migrations.head_revision()
    # older databases keep looser NOT NULL rules on added columns (SQLite cannot change that without a table
    # rebuild); every table, column and index must otherwise match the models
    drift = [d for group in migrations.schema_drift(engine) for d in (group if isinstance(group, list) else [group])]
    assert [d for d in drift if d[0] != "modify_nullable"] == []
    assert "ix_incidents_beacon_id" in {i["name"] for i in inspect(engine).get_indexes("incidents")}
    with engine.connect() as c:
        row = c.execute(text("SELECT status, severity, reported_severity, reported_people_affected FROM incidents")).one()
        assert tuple(row) == ("DISPATCHED", "HIGH", "HIGH", 7)
        assert c.execute(text("SELECT COUNT(*) FROM volunteers")).scalar() == 1


def test_already_current_database_needs_no_backup(engine):
    migrations.ensure_schema(engine)
    migrations.ensure_schema(engine)
    assert not settings.BACKUP_DIR.exists() or list(settings.BACKUP_DIR.glob("*.db.bak")) == []


def test_pending_migration_on_managed_database_is_backed_up_first(engine):
    migrations.ensure_schema(engine)
    with engine.begin() as c:
        c.execute(text("UPDATE alembic_version SET version_num = '0000'"))  # simulate "older revision"
    # 0000 is unknown, so Alembic cannot upgrade: the point is that we back up BEFORE touching it
    with pytest.raises(Exception):
        migrations.ensure_schema(engine)
    assert len(list(settings.BACKUP_DIR.glob("*pre-migration*.db.bak"))) == 1


def test_if_backup_fails_database_is_not_changed(engine, monkeypatch):
    _make_legacy_db(engine)
    before = _columns(engine)

    def boom(*a, **k):
        raise backup_mod.BackupError("disk full")

    monkeypatch.setattr(backup_mod, "create_backup", boom)
    with pytest.raises(migrations.MigrationError, match="NOT changed"):
        migrations.ensure_schema(engine)
    assert _columns(engine) == before
    assert migrations.current_revision(engine) is None


def test_invalid_environment_name_is_refused():
    r = subprocess.run([sys.executable, "-c", "import app.core.config"], cwd=BACKEND,
                       env={"RESCUENET_ENV": "staging", "PATH": "/usr/bin"}, capture_output=True, text=True)
    assert r.returncode != 0 and "RESCUENET_ENV" in r.stderr


def test_environment_defaults_to_production():
    r = subprocess.run([sys.executable, "-c", "from app.core.config import settings;print(settings.RESCUENET_ENV)"],
                       cwd=BACKEND, env={"PATH": "/usr/bin"}, capture_output=True, text=True)
    assert r.stdout.strip() == "production"


def test_ensure_schema_works_when_nothing_else_imported_the_models(tmp_path):
    """Regression: a standalone caller (script, shell) must not need to import the models first."""
    db = tmp_path / "solo.db"
    sqlite3.connect(db).executescript("CREATE TABLE incidents (id VARCHAR(50) PRIMARY KEY, severity VARCHAR(20), people_affected INTEGER);")
    code = ("from app.db.session import engine\nfrom app.db import migrations as m\n"
            "from sqlalchemy import inspect\n"
            "import app.db.migrations\n"
            "print('ok')\n")
    env = {"PATH": "/usr/bin", "DATABASE_URL": f"sqlite:///{db}", "BACKUP_DIR": str(tmp_path / "bk"), "RESCUENET_ENV": "development"}
    r = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    run = ("from app.db.session import engine\nfrom app.db.migrations import ensure_schema, current_revision, head_revision\n"
           "ensure_schema(engine)\nassert current_revision(engine) == head_revision()\nprint('adopted')")
    r = subprocess.run([sys.executable, "-c", run], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert "adopted" in r.stdout, r.stdout + r.stderr


def test_adopted_legacy_database_gets_s0_changes_through_the_migration(engine):
    """Adoption stops at the 0001 shape, so migration 0002 (not the legacy helper) adds public refs and media."""
    _make_legacy_db(engine)
    migrations.ensure_schema(engine)
    with engine.connect() as c:
        ref = c.execute(text("SELECT public_ref, tracking_code_hash FROM incidents WHERE id='INC-LEG'")).one()
        assert ref[0].startswith("RN-") and len(ref[0]) == 17
        assert ref[1] is None   # no tracking code was ever issued for a pre-existing report
    assert "media_assets" in inspect(engine).get_table_names()


def test_0002_up_down_up_preserves_incident_rows(engine):
    migrations.upgrade(engine, "0001")
    with engine.begin() as c:
        c.execute(text("INSERT INTO incidents (id,title,description,area,latitude,longitude,severity,people_affected,"
                       "status,source,data_label,created_at,updated_at) VALUES ('INC-A','t','d','a',1,1,'LOW',1,'REPORTED',"
                       "'CITIZEN_REPORT','SIMULATED','2025-01-01','2025-01-01')"))
    migrations.upgrade(engine)
    with engine.connect() as c:
        refs = [r[0] for r in c.execute(text("SELECT public_ref FROM incidents"))]
    assert len(refs) == 1 and refs[0].startswith("RN-")
    migrations.downgrade(engine, "0001")
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM incidents")).scalar() == 1
    migrations.upgrade(engine)
    assert migrations.schema_drift(engine) == []
