"""Restore the RescueNet X database from a verified backup.

    python scripts/restore_db.py PATH_TO_BACKUP --yes

STOP THE APPLICATION FIRST. The backup is verified against its manifest (checksum, integrity, row counts).
The database being replaced is saved as a 'pre-restore' backup before anything changes, so a restore can
itself be undone. Without --yes nothing is changed.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.db.backup import BackupError, restore_backup, sqlite_path_from_url, verify_backup  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backup")
    ap.add_argument("--yes", action="store_true", help="actually perform the restore")
    ap.add_argument("--backup-dir", default=str(settings.BACKUP_DIR))
    args = ap.parse_args()
    try:
        db_path = sqlite_path_from_url(settings.DATABASE_URL)
        m = verify_backup(Path(args.backup))
        print(f"Backup verified: {m['backup_file']} (sha256 {m['sha256'][:16]}..., {len(m['table_row_counts'])} tables)")
        if not args.yes:
            print(f"Dry run. Would replace {db_path}. Re-run with --yes after stopping the application.")
            return 0
        safety = restore_backup(Path(args.backup), db_path, Path(args.backup_dir))
        print(f"Restored into {db_path}")
        if safety:
            print(f"The previous database was saved as {safety}")
        return 0
    except BackupError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
