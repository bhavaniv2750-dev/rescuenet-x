"""Safely disable known demo accounts in an EXISTING database (S5 maintenance / migration).

Older versions created demo accounts (admin, commander, ...) with a password that was printed in the README and in the Git history,
so those accounts are permanently unsuitable for any real use. This tool finds them and DISABLES them. It never deletes anything.

    python scripts/disable_demo_accounts.py                         # DRY RUN: lists what would change, changes nothing
    python scripts/disable_demo_accounts.py --apply --confirm "DISABLE DEMO ACCOUNTS" --reason "go-live, ticket 9" --i-am-authorized

Run it on the server that owns the database. It cannot reach, and must not be pointed at, anyone else's machine.

How accounts are recognised (a username alone is NEVER enough, so a real person who happens to be called "operator" is safe)
  * FLAG        the account has is_demo = true (every fixture created since S5), or
  * FINGERPRINT username AND full name AND email all equal the values the old seeder wrote (the full list is DEMO_ACCOUNTS in
                app/db/seed_users.py; the earlier admin full name "System Administrator" is accepted only together with the demo
                address admin@rescuenet.local), or
  * --also-check-password   additionally prompts for a password (hidden input) and flags an account that matches a username from the
                list AND signs in with it. Use it to test the historic default; the value is never stored or printed.
Accounts that only resemble a demo account (same username, different name/email) are listed as NOT TOUCHED.

Applying: a verified backup is taken first (the run stops if it cannot be), each matched account is set inactive, flagged is_demo,
all its sessions are revoked (token version bumped), and an audit entry is written. It refuses to leave the deployment with no
active administrator unless --allow-no-admin is given (then scripts/bootstrap_admin.py creates the first real one).
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.security import verify_password  # noqa: E402
from app.db import backup as backup_mod  # noqa: E402
from app.db.migrations import ensure_schema  # noqa: E402
from app.db.seed_users import DEMO_ACCOUNTS  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.entities import User  # noqa: E402
from app.services import sessions as sess  # noqa: E402
from app.services.audit import record_audit  # noqa: E402

CONFIRM_PHRASE = "DISABLE DEMO ACCOUNTS"
LEGACY_NAMES = {"admin": "System Administrator"}      # the pre-S5 seeder's admin full name


def classify(user, check_password):
    """Returns (reason or None). A match needs a reliable fingerprint, not a name."""
    if user.is_demo:
        return "FLAG is_demo"
    for username, name, role, _team, _vol, email in DEMO_ACCOUNTS:
        if user.username != username:
            continue
        names = {name, LEGACY_NAMES.get(username, name)}
        if user.full_name in names and (user.email or "").lower() == email.lower() and user.role == role:
            return "FINGERPRINT username+name+email+role"
        if check_password and verify_password(check_password, user.password_hash):
            return "PASSWORD matched the one supplied"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--i-am-authorized", action="store_true")
    ap.add_argument("--allow-no-admin", action="store_true")
    ap.add_argument("--also-check-password", action="store_true")
    args = ap.parse_args()

    ensure_schema(engine)
    pw = getpass.getpass("Password to test against demo usernames (not stored): ") if args.also_check_password else None
    names = {a[0] for a in DEMO_ACCOUNTS}
    db = SessionLocal()
    try:
        matched, untouched = [], []
        for u in db.query(User).order_by(User.id).all():
            why = classify(u, pw)
            if why:
                matched.append((u, why))
            elif u.username in names:
                untouched.append(u)
        print(f"{'APPLY' if args.apply else 'DRY RUN'}: {len(matched)} demo account(s) recognised.")
        for u, why in matched:
            print(f"  would disable  {u.username:<12} {u.role:<15} active={u.is_active}  [{why}]" if not args.apply
                  else f"  disabling      {u.username:<12} {u.role:<15} [{why}]")
        for u in untouched:
            print(f"  NOT TOUCHED    {u.username:<12} {u.role:<15} (only the username resembles a demo account)")
        if not args.apply:
            print("Nothing was changed. Re-run with --apply --confirm \"%s\" --reason ... --i-am-authorized to disable them." % CONFIRM_PHRASE)
            return 0
        if args.confirm != CONFIRM_PHRASE or not args.i_am_authorized or len(args.reason.strip()) < 8:
            print(f"Refused: --apply needs --confirm \"{CONFIRM_PHRASE}\", --i-am-authorized and a --reason of 8+ characters.", file=sys.stderr)
            return 2
        targets = [u for u, _ in matched if u.is_active]
        if not targets:
            print("No active demo account to disable.")
            return 0
        remaining_admins = db.query(User).filter(User.role == "ADMIN", User.is_active.is_(True)).count() - sum(1 for u in targets if u.role == "ADMIN")
        if remaining_admins <= 0 and not args.allow_no_admin:
            print("Refused: this would leave NO active administrator. Create one first (invite / bootstrap) or pass --allow-no-admin "
                  "and run scripts/bootstrap_admin.py afterwards.", file=sys.stderr)
            return 3
        if engine.dialect.name == "sqlite":
            path = backup_mod.sqlite_path_from_url(str(engine.url))
            if path.is_file():
                bk = backup_mod.create_backup(path, settings.BACKUP_DIR, "pre-disable-demo")
                backup_mod.verify_backup(bk)
                print(f"Backup written and verified: {bk.name}")
        actor = f"cli:{getpass.getuser()}"
        reasons = dict((u.id, why) for u, why in matched)
        for u in targets:
            u.is_active, u.is_demo = False, True
            sess.revoke_all_sessions(db, u, "DEMO_ACCOUNT_DISABLED", actor=actor, role="HOST_OPERATOR")
            record_audit(db, actor, "DEMO_ACCOUNT_DISABLED", "user", u.id, f"{u.username} ({u.role}); {reasons[u.id]}; reason: {args.reason}"[:480],
                         role="HOST_OPERATOR")
        db.commit()
        print(f"Disabled {len(targets)} account(s); sessions revoked; nothing deleted. Records they created are untouched.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
