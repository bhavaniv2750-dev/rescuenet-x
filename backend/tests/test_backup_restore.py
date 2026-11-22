"""M0: backup / restore procedure."""

import json
import sqlite3

import pytest

from app.db import backup as b


def _make_db(path, rows=3):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE people (id INTEGER PRIMARY KEY, secret_note TEXT)")
    conn.executemany("INSERT INTO people (secret_note) VALUES (?)", [(f"PRIVATE-NOTE-{i}",) for i in range(rows)])
    conn.commit()
    conn.close()
    return path


def test_backup_is_consistent_verified_and_private(tmp_path):
    db = _make_db(tmp_path / "live.db")
    bk = b.create_backup(db, tmp_path / "bk", "unit")
    m = b.verify_backup(bk)
    assert m["integrity_check"] == "ok" and m["table_row_counts"] == {"people": 3}
    assert (bk.stat().st_mode & 0o077) == 0, "backup must be readable by the owner only"
    # the manifest holds names and counts only, never record contents
    assert "PRIVATE-NOTE" not in b.manifest_path(bk).read_text()


def test_restore_round_trip_and_safety_copy(tmp_path):
    db = _make_db(tmp_path / "live.db")
    bk = b.create_backup(db, tmp_path / "bk", "before")
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM people")
    conn.execute("INSERT INTO people (secret_note) VALUES ('changed-after-backup')")
    conn.commit()
    conn.close()

    safety = b.restore_backup(bk, db, tmp_path / "bk")

    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM people").fetchone()[0] == 3
    assert safety is not None and "pre-restore" in safety.name
    # the state we replaced is still recoverable
    assert sqlite3.connect(safety).execute("SELECT secret_note FROM people").fetchone()[0] == "changed-after-backup"
    assert b.sha256_file(bk) == json.loads(b.manifest_path(bk).read_text())["sha256"]  # backup itself unchanged


def test_tampered_backup_is_rejected_and_live_db_untouched(tmp_path):
    db = _make_db(tmp_path / "live.db")
    bk = b.create_backup(db, tmp_path / "bk")
    live_hash = b.sha256_file(db)
    with open(bk, "r+b") as fh:
        fh.seek(-10, 2)
        fh.write(b"\x00" * 10)
    with pytest.raises(b.BackupError, match="Checksum"):
        b.restore_backup(bk, db, tmp_path / "bk")
    assert b.sha256_file(db) == live_hash


def test_backup_without_manifest_is_not_trusted(tmp_path):
    db = _make_db(tmp_path / "live.db")
    bk = b.create_backup(db, tmp_path / "bk")
    b.manifest_path(bk).unlink()
    with pytest.raises(b.BackupError, match="Manifest missing"):
        b.restore_backup(bk, db, tmp_path / "bk")


def test_backup_never_overwrites_and_never_touches_source(tmp_path):
    db = _make_db(tmp_path / "live.db")
    before = b.sha256_file(db)
    first = b.create_backup(db, tmp_path / "bk", "x")
    second = b.create_backup(db, tmp_path / "bk", "x")
    assert first != second and first.exists() and second.exists()
    assert b.sha256_file(db) == before


def test_missing_database_and_memory_database_are_refused(tmp_path):
    with pytest.raises(b.BackupError):
        b.create_backup(tmp_path / "nope.db", tmp_path / "bk")
    with pytest.raises(b.BackupError):
        b.sqlite_path_from_url("sqlite:///:memory:")
    with pytest.raises(b.BackupError):
        b.sqlite_path_from_url("postgresql://x/y")


def test_restore_cli_dry_run_changes_nothing(tmp_path):
    import os, subprocess, sys
    from pathlib import Path
    backend = Path(__file__).resolve().parent.parent
    db = _make_db(tmp_path / "live.db")
    bk = b.create_backup(db, tmp_path / "bk")
    before = b.sha256_file(db)
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "BACKUP_DIR": str(tmp_path / "bk")}
    r = subprocess.run([sys.executable, str(backend / "scripts" / "restore_db.py"), str(bk)],
                       cwd=backend, env=env, capture_output=True, text=True)
    assert r.returncode == 0 and "Dry run" in r.stdout
    assert b.sha256_file(db) == before
