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


# ---------------------------------------------------------------- S2: revision 0003 (sessions)

def test_0003_adds_session_tables_and_token_version_without_touching_users(engine):
    migrations.upgrade(engine, "0002")
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (username, full_name, role, password_hash, is_active, failed_logins, created_at) "
                       "VALUES ('legacy_user','Legacy','OPERATOR','hash-not-real',1,0,'2025-01-01')"))
    migrations.upgrade(engine)
    insp = inspect(engine)
    assert {"auth_sessions", "refresh_tokens"} <= set(insp.get_table_names())
    cols = {c["name"] for c in insp.get_columns("users")}
    assert {"token_version", "password_changed_at"} <= cols
    with engine.connect() as c:
        row = c.execute(text("SELECT username, role, password_hash, token_version FROM users")).one()
        assert tuple(row) == ("legacy_user", "OPERATOR", "hash-not-real", 0)        # untouched; version starts at 0
        assert c.execute(text("SELECT COUNT(*) FROM auth_sessions")).scalar() == 0      # nobody has a session: everyone signs in again
    assert migrations.schema_drift(engine) == []


def test_0003_up_down_up_preserves_users(engine):
    migrations.upgrade(engine, "0002")
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (username, full_name, role, password_hash, is_active, failed_logins, created_at) "
                       "VALUES ('keep_me','Keep','CITIZEN','h',1,0,'2025-01-01')"))
    migrations.upgrade(engine)
    migrations.downgrade(engine, "0002")
    assert "auth_sessions" not in inspect(engine).get_table_names()
    assert "token_version" not in {c["name"] for c in inspect(engine).get_columns("users")}
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM users WHERE username='keep_me'")).scalar() == 1
    migrations.upgrade(engine)
    assert migrations.schema_drift(engine) == []


def test_existing_database_is_backed_up_before_the_sessions_migration(engine):
    migrations.upgrade(engine, "0002")
    migrations.ensure_schema(engine)          # a managed database one revision behind head
    assert migrations.current_revision(engine) == migrations.head_revision()
    assert len(list(settings.BACKUP_DIR.glob("*pre-migration*.db.bak"))) == 1


# ---------------------------------------------------------------- S3: revision 0004

def test_0004_adds_contact_recovery_and_rate_limit_structures_without_marking_anything_verified(engine):
    migrations.upgrade(engine, "0003")
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (username, full_name, role, email, password_hash, is_active, failed_logins, token_version, created_at) "
                       "VALUES ('old_user','Old','CITIZEN','old@example.org','h',1,0,0,'2025-01-01')"))
    migrations.upgrade(engine)
    insp = inspect(engine)
    assert {"one_time_tokens", "notification_outbox", "rate_limit_events"} <= set(insp.get_table_names())
    assert {"email_verified_at", "phone_verified_at", "email_changed_at", "must_change_password"} <= {c["name"] for c in insp.get_columns("users")}
    with engine.connect() as c:
        row = c.execute(text("SELECT email, email_verified_at, phone_verified_at, must_change_password FROM users")).one()
        assert tuple(row) == ("old@example.org", None, None, 0)        # existing addresses stay UNVERIFIED; nobody is forced to change a password
    assert migrations.schema_drift(engine) == []


def test_0004_up_down_up_keeps_users_and_the_sessions_tables(engine):
    migrations.upgrade(engine, "0003")
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (username, full_name, role, password_hash, is_active, failed_logins, token_version, created_at) "
                       "VALUES ('keep','Keep','CITIZEN','h',1,0,0,'2025-01-01')"))
    migrations.upgrade(engine)
    migrations.downgrade(engine, "0003")
    assert "rate_limit_events" not in inspect(engine).get_table_names() and "auth_sessions" in inspect(engine).get_table_names()
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM users WHERE username='keep'")).scalar() == 1
    migrations.upgrade(engine)
    assert migrations.schema_drift(engine) == []


# ---------------------------------------------------------------- S4: revision 0005 (MFA)

def _seed_pre_mfa(engine):
    """A database as S3 left it: privileged and public accounts, a live session, an unverified email."""
    migrations.upgrade(engine, "0004")
    with engine.begin() as c:
        for i, (name, role) in enumerate([("cmdr", "COMMANDER"), ("oper", "OPERATOR"), ("adm", "ADMIN"), ("offc", "RESCUE_OFFICER"), ("cit", "CITIZEN")], start=1):
            c.execute(text("INSERT INTO users (id, username, full_name, role, email, password_hash, is_active, failed_logins, token_version, "
                           "must_change_password, created_at) VALUES (:i,:n,:n,:r,:e,'hash-not-real',1,0,0,0,'2025-01-01')"),
                      {"i": i, "n": name, "r": role, "e": f"{name}@example.org"})
        c.execute(text("INSERT INTO auth_sessions (id, user_id, created_at, last_used_at, expires_at, idle_timeout_s, remember) "
                       "VALUES ('s1', 1, '2026-01-01', '2026-01-01', '2999-01-01', 3600, 0)"))


def test_0005_keeps_every_existing_account_and_marks_nobody_as_enrolled(engine):
    _seed_pre_mfa(engine)
    migrations.upgrade(engine)
    insp = inspect(engine)
    assert {"mfa_credentials", "mfa_recovery_codes", "auth_challenges"} <= set(insp.get_table_names())
    assert {"assurance", "mfa_at", "mfa_method"} <= {c["name"] for c in insp.get_columns("auth_sessions")}
    with engine.connect() as c:
        rows = c.execute(text("SELECT username, role, password_hash, is_active FROM users ORDER BY id")).all()
        assert [tuple(r) for r in rows] == [("cmdr", "COMMANDER", "hash-not-real", 1), ("oper", "OPERATOR", "hash-not-real", 1),
                                             ("adm", "ADMIN", "hash-not-real", 1), ("offc", "RESCUE_OFFICER", "hash-not-real", 1),
                                             ("cit", "CITIZEN", "hash-not-real", 1)]
        for t in ("mfa_credentials", "mfa_recovery_codes", "auth_challenges"):
            assert c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() == 0                  # nobody was silently marked MFA-verified
        assert c.execute(text("SELECT assurance, mfa_at FROM auth_sessions WHERE id='s1'")).one() == ("PASSWORD", None)
    assert migrations.schema_drift(engine) == []


def test_existing_privileged_accounts_are_restricted_until_they_enrol_after_the_migration(engine):
    from sqlalchemy.orm import Session as OrmSession
    from app.models.entities import AuthSession, User
    from app.services import auth_state as astate
    _seed_pre_mfa(engine)
    migrations.upgrade(engine)
    with OrmSession(engine) as db:
        s = db.get(AuthSession, "s1")
        for username, expected in [("cmdr", astate.MFA_ENROLLMENT_PENDING), ("oper", astate.MFA_ENROLLMENT_PENDING),
                                   ("adm", astate.MFA_ENROLLMENT_PENDING), ("offc", astate.MFA_ENROLLMENT_PENDING), ("cit", astate.AUTHENTICATED)]:
            u = db.query(User).filter(User.username == username).one()
            assert astate.session_state(u, s, False) == expected, username
            assert astate.path_allowed(astate.session_state(u, s, False), "/api/teams/") == (expected == astate.AUTHENTICATED)


def test_0005_up_down_up_preserves_users_and_sessions(engine):
    _seed_pre_mfa(engine)
    migrations.upgrade(engine)
    migrations.downgrade(engine, "0004")
    insp = inspect(engine)
    assert "mfa_credentials" not in insp.get_table_names() and "assurance" not in {c["name"] for c in insp.get_columns("auth_sessions")}
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM users")).scalar() == 5 and c.execute(text("SELECT COUNT(*) FROM auth_sessions")).scalar() == 1
    migrations.upgrade(engine)
    assert migrations.schema_drift(engine) == []


def test_0005_is_backed_up_first_and_the_backup_restores_the_pre_migration_state(engine, tmp_path):
    import sqlite3
    from app.db import backup as backup_mod
    _seed_pre_mfa(engine)
    db_file = backup_mod.sqlite_path_from_url(str(engine.url))
    migrations.ensure_schema(engine)                                       # managed DB one revision behind: backs up, then upgrades
    backups = sorted(settings.BACKUP_DIR.glob("*pre-migration*.db.bak"))
    assert len(backups) == 1
    manifest = backup_mod.verify_backup(backups[0])                        # checksum, integrity and row counts match
    assert manifest["table_row_counts"]["users"] == 5 and "mfa_credentials" not in manifest["table_row_counts"]
    engine.dispose()
    backup_mod.restore_backup(backups[0], db_file, settings.BACKUP_DIR)
    raw = sqlite3.connect(db_file)
    tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "mfa_credentials" not in tables and raw.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 5
    assert raw.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0004"
    raw.close()


# ---------------------------------------------------------------- S5: revision 0006 (agencies, invitations, activation flags)

def _seed_pre_s5(engine):
    """A database as S4 left it: privileged and public accounts (some with an unverified address), a team, MFA rows."""
    migrations.upgrade(engine, "0005")
    with engine.begin() as c:
        for i, (name, role) in enumerate([("cmdr", "COMMANDER"), ("adm", "ADMIN"), ("offc", "RESCUE_OFFICER"), ("cit", "CITIZEN")], start=1):
            c.execute(text("INSERT INTO users (id, username, full_name, role, email, password_hash, is_active, failed_logins, token_version, "
                           "must_change_password, created_at) VALUES (:i,:n,:n,:r,:e,'hash-not-real',1,0,0,0,'2025-01-01')"),
                      {"i": i, "n": name, "r": role, "e": f"{name}@example.org"})
        c.execute(text("INSERT INTO rescue_teams (id, name, callsign, status, vehicle_type, members_count, skills, latitude, longitude, base_station, "
                       "contact_number) VALUES ('T1','Team','Call','AVAILABLE','boat',4,'x',12.9,77.6,'base','100')"))
        c.execute(text("INSERT INTO mfa_credentials (user_id, secret_enc, status, created_at) VALUES (1,'enc','ACTIVE','2025-01-01')"))


def test_0006_adds_the_new_structures_and_changes_no_existing_account(engine):
    _seed_pre_s5(engine)
    migrations.upgrade(engine)
    insp = inspect(engine)
    assert {"agencies", "invitations"} <= set(insp.get_table_names())
    ucols = {c["name"] for c in insp.get_columns("users")}
    assert {"agency_id", "contact_verification_required", "contact_verification_waived_at", "is_demo"} <= ucols
    assert "agency_id" in {c["name"] for c in insp.get_columns("rescue_teams")}
    with engine.connect() as c:
        rows = c.execute(text("SELECT username, role, password_hash, is_active, email, email_verified_at, contact_verification_required, "
                              "contact_verification_waived_at, is_demo, agency_id FROM users ORDER BY id")).all()
        assert [tuple(r) for r in rows] == [(n, r, "hash-not-real", 1, f"{n}@example.org", None, 0, None, 0, None)
                                             for n, r in [("cmdr", "COMMANDER"), ("adm", "ADMIN"), ("offc", "RESCUE_OFFICER"), ("cit", "CITIZEN")]]
        assert c.execute(text("SELECT COUNT(*) FROM agencies")).scalar() == 0 and c.execute(text("SELECT COUNT(*) FROM invitations")).scalar() == 0
        assert c.execute(text("SELECT COUNT(*) FROM mfa_credentials")).scalar() == 1               # MFA enrolment untouched
        assert c.execute(text("SELECT agency_id FROM rescue_teams")).scalar() is None
    assert migrations.schema_drift(engine) == []                                                    # models and migration agree


def test_0006_up_down_up_preserves_accounts_and_drops_only_the_new_structures(engine):
    _seed_pre_s5(engine)
    migrations.upgrade(engine)
    with engine.begin() as c:
        c.execute(text("INSERT INTO agencies (name, agency_type, is_active, created_at, updated_at) VALUES ('A','FIRE_EMERGENCY',1,'2026-01-01','2026-01-01')"))
        c.execute(text("UPDATE users SET agency_id=1, is_demo=1 WHERE id=1"))
    migrations.downgrade(engine, "0005")
    insp = inspect(engine)
    assert not ({"agencies", "invitations"} & set(insp.get_table_names()))
    assert not ({"agency_id", "is_demo", "contact_verification_required", "contact_verification_waived_at"} & {c["name"] for c in insp.get_columns("users")})
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM users")).scalar() == 4 and c.execute(text("SELECT COUNT(*) FROM rescue_teams")).scalar() == 1
        assert c.execute(text("SELECT COUNT(*) FROM mfa_credentials")).scalar() == 1
    migrations.upgrade(engine)
    assert migrations.schema_drift(engine) == []


def test_0006_is_backed_up_first_and_the_backup_restores_the_pre_migration_state(engine, tmp_path):
    _seed_pre_s5(engine)
    db_file = backup_mod.sqlite_path_from_url(str(engine.url))
    migrations.ensure_schema(engine)
    backups = sorted(settings.BACKUP_DIR.glob("*pre-migration*.db.bak"))
    assert len(backups) == 1
    manifest = backup_mod.verify_backup(backups[0])
    assert manifest["table_row_counts"]["users"] == 4 and "agencies" not in manifest["table_row_counts"]
    engine.dispose()
    backup_mod.restore_backup(backups[0], db_file, settings.BACKUP_DIR)
    raw = sqlite3.connect(db_file)
    assert "agencies" not in {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert raw.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 4
    assert raw.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005"
    raw.close()


def test_existing_privileged_accounts_keep_working_under_the_development_policy_and_need_verification_under_production_policy(engine, monkeypatch):
    from sqlalchemy.orm import Session as OrmSession
    from app.models.entities import User
    from app.services import auth_state as astate
    _seed_pre_s5(engine)
    migrations.upgrade(engine)
    with OrmSession(engine) as db:
        cmdr = db.query(User).filter(User.username == "cmdr").one()
        monkeypatch.setattr(settings, "PRIVILEGED_REQUIRE_VERIFIED_EMAIL", False)
        assert not astate.contact_verification_pending(cmdr)
        monkeypatch.setattr(settings, "PRIVILEGED_REQUIRE_VERIFIED_EMAIL", True)
        assert astate.contact_verification_pending(cmdr)                      # unverified address: needs a code, or a host waiver
        assert not astate.contact_verification_pending(db.query(User).filter(User.username == "cit").one())     # public roles: not required
