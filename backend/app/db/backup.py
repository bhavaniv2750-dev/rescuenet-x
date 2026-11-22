"""SQLite backup and restore with integrity checks.

A backup is taken with SQLite's online backup API, so it is consistent even while the app is running.
Every backup gets a manifest (SHA-256, size, integrity result, table row counts) next to it. A restore
verifies the backup against that manifest first, keeps a copy of the database it replaces, and swaps the
file in atomically. Nothing here ever deletes a database or a backup.

Only table names and row counts go into the manifest. Record contents are never read into it or logged.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class BackupError(RuntimeError):
    pass


def sqlite_path_from_url(url: str) -> Path:
    """Return the file path of a sqlite:/// URL. Raises for anything that is not a file-backed SQLite database."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise BackupError("Backups are only supported for file-based SQLite databases.")
    raw = url[len(prefix):].split("?", 1)[0]
    if raw in ("", ":memory:"):
        raise BackupError("An in-memory database cannot be backed up.")
    return Path(raw)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def integrity_check(path: Path) -> str:
    conn = _connect_ro(path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


def table_counts(path: Path) -> dict:
    conn = _connect_ro(path)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {n: conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
    finally:
        conn.close()


def manifest_path(backup: Path) -> Path:
    return backup.with_name(backup.name + ".manifest.json")


def create_backup(db_path: Path, backup_dir: Path, label: str = "manual") -> Path:
    """Copy db_path into backup_dir and write a verified manifest. Returns the backup file path."""
    db_path = Path(db_path)
    if not db_path.is_file():
        raise BackupError(f"Database file not found: {db_path}")
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        pass
    safe_label = "".join(c for c in label if c.isalnum() or c in "-_")[:40] or "manual"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = backup_dir / f"{db_path.stem}-{stamp}-{safe_label}.db.bak"
    if target.exists():
        raise BackupError(f"Refusing to overwrite existing backup {target.name}")

    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass

    result = integrity_check(target)
    if result != "ok":
        raise BackupError(f"Backup failed its integrity check ({result}); it was kept for inspection: {target.name}")
    manifest = {
        "format": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "label": safe_label,
        "source_file": db_path.name,
        "backup_file": target.name,
        "sha256": sha256_file(target),
        "size_bytes": target.stat().st_size,
        "integrity_check": result,
        "table_row_counts": table_counts(target),
    }
    mp = manifest_path(target)
    mp.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    try:
        os.chmod(mp, 0o600)
    except OSError:
        pass
    return target


def verify_backup(backup: Path) -> dict:
    """Check a backup against its manifest. Returns the manifest or raises BackupError."""
    backup = Path(backup)
    mp = manifest_path(backup)
    if not backup.is_file():
        raise BackupError(f"Backup not found: {backup}")
    if not mp.is_file():
        raise BackupError(f"Manifest missing for {backup.name}; refusing to trust an unverified backup.")
    manifest = json.loads(mp.read_text())
    if sha256_file(backup) != manifest.get("sha256"):
        raise BackupError(f"Checksum mismatch for {backup.name}: the backup was changed after it was made.")
    if integrity_check(backup) != "ok":
        raise BackupError(f"{backup.name} fails SQLite integrity_check.")
    if table_counts(backup) != manifest.get("table_row_counts"):
        raise BackupError(f"Row counts of {backup.name} differ from its manifest.")
    return manifest


def restore_backup(backup: Path, db_path: Path, backup_dir: Path) -> Path | None:
    """Replace db_path with a verified backup. The database being replaced is first saved as a 'pre-restore'
    backup. Returns that safety backup's path (None when there was no database to replace).
    Stop the application before restoring: a running app holds the file open."""
    backup, db_path = Path(backup), Path(db_path)
    verify_backup(backup)
    safety = None
    if db_path.is_file():
        safety = create_backup(db_path, backup_dir, label="pre-restore")
    staging = db_path.with_name(db_path.name + ".restore-tmp")
    shutil.copyfile(backup, staging)
    if integrity_check(staging) != "ok":
        staging.unlink(missing_ok=True)
        raise BackupError("Staged copy failed integrity check; the live database was not touched.")
    # A leftover WAL/journal from the old database must not be replayed onto the restored file.
    for suffix in ("-wal", "-shm", "-journal"):
        stale = db_path.with_name(db_path.name + suffix)
        if stale.exists():
            stale.rename(stale.with_name(stale.name + ".replaced"))
    os.replace(staging, db_path)
    return safety
