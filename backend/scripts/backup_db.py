"""Back up the RescueNet X database.

    python scripts/backup_db.py                 # back up the configured DATABASE_URL into BACKUP_DIR
    python scripts/backup_db.py --label before-upgrade
    python scripts/backup_db.py --verify PATH   # check an existing backup against its manifest

Prints only file names, checksums and table row counts. It never prints record contents.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.db.backup import BackupError, create_backup, sqlite_path_from_url, verify_backup  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="manual")
    ap.add_argument("--verify", metavar="BACKUP", help="verify an existing backup instead of creating one")
    ap.add_argument("--backup-dir", default=str(settings.BACKUP_DIR))
    args = ap.parse_args()
    try:
        if args.verify:
            m = verify_backup(Path(args.verify))
            print(f"OK  {m['backup_file']}  sha256={m['sha256'][:16]}...  tables={len(m['table_row_counts'])}")
            return 0
        path = create_backup(sqlite_path_from_url(settings.DATABASE_URL), Path(args.backup_dir), args.label)
        m = verify_backup(path)
        print(f"Backup written and verified: {path}")
        print(f"sha256={m['sha256']}  size={m['size_bytes']} bytes  integrity={m['integrity_check']}")
        for t, n in m["table_row_counts"].items():
            print(f"  {t}: {n} rows")
        return 0
    except BackupError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
