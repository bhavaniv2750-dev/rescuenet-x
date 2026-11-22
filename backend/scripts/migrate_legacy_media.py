"""Move photos stored by the old public upload route under the new private-media rules.

    python scripts/migrate_legacy_media.py            # dry run: counts only, nothing is written
    python scripts/migrate_legacy_media.py --apply    # import (take a backup first: scripts/backup_db.py)

Original files are never deleted or changed. Prints counts and incident ids only, never record contents.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.init_db import init_db  # noqa: E402  (makes sure the schema is current)
from app.db.session import SessionLocal  # noqa: E402
from app.services.media import import_legacy_uploads  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    init_db()
    db = SessionLocal()
    try:
        r = import_legacy_uploads(db, apply=args.apply)
    finally:
        db.close()
    print(f"legacy photos found: {r['found']}; importable: {r['importable']}; imported: {r['imported']}")
    if r["missing_file"]:
        print(f"file missing for incidents: {', '.join(r['missing_file'])}")
    if r["rejected"]:
        print(f"not a valid photo (left untouched) for incidents: {', '.join(r['rejected'])}")
    if not args.apply:
        print("Dry run. Re-run with --apply after taking a backup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
