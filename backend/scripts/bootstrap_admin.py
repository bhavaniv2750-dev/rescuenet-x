"""Create the FIRST administrator of a new deployment (host-authorised, one time).

There is no default account, no default password and no web endpoint for this. Someone with shell access to the server, who the
organisation has separately authorised, runs it once:

  Linux / macOS (from the repository root, with the backend environment active):
      cd backend
      python scripts/bootstrap_admin.py --username firstadmin --full-name "Asha Rao" --email asha@example.org \
          --reason "initial deployment, ticket 1" --i-am-authorized

  Windows (PowerShell):
      cd backend
      python scripts\bootstrap_admin.py --username firstadmin --full-name "Asha Rao" --email asha@example.org `
          --reason "initial deployment, ticket 1" --i-am-authorized

What it does
* refuses unless the database is migrated and NO active, non-demo administrator exists (so it cannot be run again to add a
  second administrator or to take over; later privileged accounts come from invitations: scripts/account_admin.py invite);
* takes a verified backup first;
* generates a random one-time password and prints it ONCE (never stored in clear, never written to a file or log);
* the account must change that password at first sign-in, enrol MFA (mandatory) and verify the --email address (a code is sent
  to it; with no email provider the host operator must waive that single step: account_admin.py waive-contact-verification);
* writes an audit record (actor "cli:<operating-system user>").
After the demo accounts of an older database were disabled with scripts/disable_demo_accounts.py, this is how the first real
administrator is created.
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import backup as backup_mod  # noqa: E402
from app.db.migrations import ensure_schema  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.entities import User  # noqa: E402
from app.services import provisioning as prov  # noqa: E402
from app.services.audit import record_audit  # noqa: E402


def active_real_admin_exists(db) -> bool:
    return db.query(User).filter(User.role == "ADMIN", User.is_active.is_(True), User.is_demo.is_(False)).first() is not None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", required=True)
    ap.add_argument("--full-name", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--i-am-authorized", action="store_true")
    args = ap.parse_args()
    if not args.i_am_authorized or len(args.reason.strip()) < 8:
        print("Refused: pass --i-am-authorized and a --reason of at least 8 characters.", file=sys.stderr)
        return 2
    email = prov.ver.normalise_email(args.email)
    username = args.username.strip().lower()
    if not (email and prov.EMAIL_RE.match(email)) or len(username) < 3:
        print("Refused: a valid --email and a --username of at least 3 characters are required.", file=sys.stderr)
        return 1

    ensure_schema(engine)
    db = SessionLocal()
    try:
        if active_real_admin_exists(db):
            print("Refused: an active administrator already exists. Bootstrap is a one-time operation; use "
                  "'account_admin.py invite' to add privileged accounts.", file=sys.stderr)
            return 3
        if db.query(User).filter(User.username == username).first():
            print(f"Refused: username '{username}' already exists.", file=sys.stderr)
            return 1
        if engine.dialect.name == "sqlite":
            path = backup_mod.sqlite_path_from_url(str(engine.url))
            if path.is_file():
                bk = backup_mod.create_backup(path, settings.BACKUP_DIR, "pre-bootstrap-admin")
                backup_mod.verify_backup(bk)
                print(f"Backup written and verified: {bk.name}")
        password = prov.one_time_password()
        actor = f"cli:{getpass.getuser()}"
        user = User(username=username, full_name=args.full_name.strip(), role="ADMIN", email=email,
                    password_hash=hash_password(password), must_change_password=True, contact_verification_required=True)
        db.add(user)
        db.flush()
        record_audit(db, actor, "FIRST_ADMIN_BOOTSTRAPPED", "user", user.id, f"{username}; reason: {args.reason}"[:480], role="HOST_OPERATOR")
        db.commit()
        print(f"First administrator '{username}' created. Sign in through the Admin portal.")
        print(f"One-time password (shown once, not stored anywhere in clear): {password}")
        print("They must change it at first sign-in, then enrol MFA and verify the email address.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
