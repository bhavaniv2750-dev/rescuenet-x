"""Host-level account provisioning and recovery (break-glass). Not reachable through the web API.

Administrators in the web console can NOT create staff accounts or reset staff passwords (that would let an
administrator obtain operational authority). Until owner-controlled invitation and recovery exist (milestones S3-S5),
a person with SHELL ACCESS TO THE SERVER, authorised separately from the application's administrators, uses this tool:

    python scripts/account_admin.py create --username jdoe --role OPERATOR --full-name "J Doe" \
        --reason "new shift operator, ticket 123" --i-am-authorized
    python scripts/account_admin.py reset-password --username jdoe --reason "locked out, identity verified in person" \
        --i-am-authorized

* A verified database backup is taken first.
* A random one-time password is generated and printed ONCE to this terminal. Hand it to the account owner out of band.
  It is never written to a file or a log; only its salted PBKDF2 hash is stored.
* The account is flagged "must change password": until the owner has chosen a new password (which cannot be the temporary
  one) every operational endpoint answers 403; only sign-in, viewing their own profile, changing the password and signing
  out work. Recovery never changes the account's role or permissions.
* Every use is recorded in the audit log (actor "cli:<operating-system user>", the reason, no secrets).
* All existing sessions of the account are ended.
"""
import argparse
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.permissions import ROLES  # noqa: E402
from app.core.security import ROLE_PORTAL, hash_password, password_problem  # noqa: E402
from app.db import backup as backup_mod  # noqa: E402
from app.db.migrations import ensure_schema  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.entities import RescueTeam, User  # noqa: E402
from app.services import rate_limit  # noqa: E402
from app.services import sessions as sess  # noqa: E402
from app.services.audit import record_audit  # noqa: E402


def one_time_password() -> str:
    while True:
        pw = secrets.token_urlsafe(14)
        if password_problem(pw) is None:
            return pw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--username", required=True)
    c.add_argument("--role", required=True, choices=ROLES)
    c.add_argument("--full-name", required=True)
    c.add_argument("--team-id")
    r = sub.add_parser("reset-password")
    r.add_argument("--username", required=True)
    for p in (c, r):
        p.add_argument("--reason", required=True, help="why this is needed (recorded in the audit log)")
        p.add_argument("--i-am-authorized", action="store_true", help="confirm you are authorised to do this on this server")
    args = ap.parse_args()
    if not args.i_am_authorized or len(args.reason.strip()) < 8:
        print("Refused: pass --i-am-authorized and a --reason of at least 8 characters.", file=sys.stderr)
        return 2

    ensure_schema(engine)
    if engine.dialect.name == "sqlite":
        path = backup_mod.sqlite_path_from_url(str(engine.url))
        if path.is_file():
            bk = backup_mod.create_backup(path, settings.BACKUP_DIR, "pre-account-admin")
            backup_mod.verify_backup(bk)
            print(f"Backup written and verified: {bk.name}")

    actor = f"cli:{getpass.getuser()}"
    username = args.username.strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        password = one_time_password()
        if args.cmd == "create":
            if user is not None:
                print(f"Refused: username '{username}' already exists.", file=sys.stderr)
                return 1
            if args.role == "RESCUE_OFFICER" and not (args.team_id and db.query(RescueTeam).filter(RescueTeam.id == args.team_id).first()):
                print("Refused: a rescue officer needs an existing --team-id.", file=sys.stderr)
                return 1
            user = User(username=username, full_name=args.full_name, role=args.role, team_id=args.team_id,
                        password_hash=hash_password(password), must_change_password=True)
            db.add(user)
            db.flush()
            record_audit(db, actor, "ACCOUNT_CLI_CREATED", "user", user.id, f"{username} as {args.role}; reason: {args.reason}", role="HOST_OPERATOR")
        else:
            if user is None:
                print(f"Refused: no account named '{username}'.", file=sys.stderr)
                return 1
            user.password_hash = hash_password(password)
            user.must_change_password = True
            user.failed_logins, user.locked_until = 0, None
            record_audit(db, actor, "ACCOUNT_CLI_PASSWORD_RESET", "user", user.id, f"{username}; reason: {args.reason}", role="HOST_OPERATOR")
            sess.revoke_all_sessions(db, user, "CLI_PASSWORD_RESET", actor=actor, role="HOST_OPERATOR")
        db.commit()
        rate_limit.clear("login-account", rate_limit.identifier_key(username))
        print(f"Account '{username}' ({user.role}) signs in through the '{ROLE_PORTAL.get(user.role)}' portal.")
        print(f"One-time password (shown once, not stored anywhere in clear): {password}")
        print("Give it to the owner out of band. They must change it at first sign-in; until then the account can do nothing else.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
