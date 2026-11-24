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
* Password recovery NEVER removes enrolled MFA: the owner still completes their authenticator challenge (or, for a privileged
  account without MFA, enrols before any operational access).

Invitations (S5): the way to onboard another ADMIN / DEVELOPER / COMMANDER / OPERATOR / RESCUE_OFFICER. The OWNER picks their
own password, so nobody else ever knows it:

    python scripts/account_admin.py invite --email jdoe@example.org --role OPERATOR [--agency-id 3] [--team-id TEAM-X] \
        [--hours 72] [--send-email] --reason "new shift operator, ticket 123" --i-am-authorized
    python scripts/account_admin.py list-invitations
    python scripts/account_admin.py revoke-invitation --id 7 --reason "wrong recipient" --i-am-authorized

* the one-time link is printed ONCE (only its SHA-256 is stored); hand it over out of band, or add --send-email (delivers only
  if an email provider is configured; the outcome is reported honestly and a development outbox delivers nothing);
* it is single use, expires (INVITATION_HOURS, max 168), is bound to that email address, role, agency and team, and can be revoked;
* the invited account has NO permission until its owner verified the address (a code sent to it) and enrolled MFA.

Existing privileged accounts that cannot verify an email address (no provider, or no address) are handled with

    python scripts/account_admin.py waive-contact-verification --username jdoe --reason "..." --i-am-authorized

which records the waiver in the audit log. It never marks an address verified and never touches MFA.

Lost authenticator (privileged accounts included) is a separate, stricter procedure:

    python scripts/account_admin.py reset-mfa --username jdoe --reason "phone lost" \
        --identity-verified "checked photo ID in person against HR record, ticket 456" --i-am-authorized

* needs a recorded reason AND a description of how the owner's identity was re-verified (>= 15 characters);
* takes a verified backup, deletes the TOTP credential and recovery codes, ends every session, audits (`ACCOUNT_CLI_MFA_RESET`);
* the password is NOT changed, and the account must RE-ENROL MFA at its next sign-in before any operational access;
* a password recovery and an MFA reset of the same privileged account must be at least RECOVERY_COMBINATION_HOURS (24) apart,
  so one operator cannot take over a commander in a single sitting. A second authorised operator may override with
  `--second-authorizer NAME` (recorded). This is policy plus audit, not cryptographic proof: see docs/security/S4_MFA.md.
"""
import argparse
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

from app.core.permissions import PRIVILEGED_ROLES, ROLES  # noqa: E402
from app.core.security import ROLE_PORTAL, hash_password, password_problem  # noqa: E402
from app.db import backup as backup_mod  # noqa: E402
from app.db.migrations import ensure_schema  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.entities import Agency, AuditLog, AuthChallenge, Invitation, RescueTeam, User  # noqa: E402
from app.services import provisioning as prov  # noqa: E402
from app.services import mfa as mfa_svc  # noqa: E402
from app.services import rate_limit  # noqa: E402
from app.services import sessions as sess  # noqa: E402
from app.services.audit import record_audit  # noqa: E402


PASSWORD_RECOVERY_ACTIONS = ("ACCOUNT_CLI_PASSWORD_RESET", "PASSWORD_RESET_COMPLETED", "USER_PASSWORD_RESET_BY_ADMIN")


from app.services.provisioning import one_time_password  # noqa: E402


def recent_recovery(db, user, actions) -> bool:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=settings.RECOVERY_COMBINATION_HOURS)
    return db.query(AuditLog).filter(AuditLog.target_type == "user", AuditLog.target_id == str(user.id),
                                     AuditLog.action.in_(actions), AuditLog.created_at > cutoff).first() is not None


def override_ok(args, actor) -> bool:
    second = (getattr(args, "second_authorizer", None) or "").strip()
    return len(second) >= 3 and second.lower() != actor.split(":", 1)[-1].lower()


def reset_mfa(db, user, username, actor, args) -> int:
    if len(args.identity_verified.strip()) < 15:
        print("Refused: --identity-verified must describe how the owner's identity was re-verified (15+ characters).", file=sys.stderr)
        return 2
    if user is None:
        print(f"Refused: no account named '{username}'.", file=sys.stderr)
        return 1
    if user.role in PRIVILEGED_ROLES and recent_recovery(db, user, PASSWORD_RECOVERY_ACTIONS) and not override_ok(args, actor):
        print(f"Refused: a password recovery of this privileged account happened in the last {settings.RECOVERY_COMBINATION_HOURS} hours. "
              "Doing the MFA reset too would let one sitting take the account over; wait, or have a second authorised operator pass "
              "--second-authorizer NAME.", file=sys.stderr)
        return 3
    had = mfa_svc.get_credential(db, user.id) is not None
    mfa_svc.remove_credential(db, user.id)
    db.query(AuthChallenge).filter(AuthChallenge.user_id == user.id).delete()
    note = f"{username}; reason: {args.reason}; identity re-verified: {args.identity_verified}"
    if getattr(args, "second_authorizer", None):
        note += f"; second authorizer: {args.second_authorizer}"
    record_audit(db, actor, "ACCOUNT_CLI_MFA_RESET", "user", user.id, note[:480], role="HOST_OPERATOR")
    sess.revoke_all_sessions(db, user, "CLI_MFA_RESET", actor=actor, role="HOST_OPERATOR")
    db.commit()
    rate_limit.clear("mfa-fail", str(user.id))
    print(f"MFA reset for '{username}' ({user.role}); {'a credential was removed' if had else 'there was no credential'}. "
          "All sessions ended. The password is unchanged.")
    print("The owner must enrol MFA again at their next sign-in; until then the account can do nothing operational.")
    return 0


def invite(db, actor, args) -> int:
    try:
        inv, token = prov.issue_invitation(db, role=args.role, email=args.email, actor=actor, reason=args.reason,
                                           agency_id=args.agency_id, team_id=args.team_id, hours=args.hours)
    except prov.InvitationError as exc:
        db.rollback()
        print(f"Refused: {exc}", file=sys.stderr)
        return 1
    db.commit()
    link = prov.invitation_link(token)
    print(f"Invitation #{inv.id}: {inv.role} for {inv.recipient_email}, expires {inv.expires_at:%Y-%m-%d %H:%M} UTC.")
    print(f"One-time link (shown once, not stored anywhere in clear): {link}")
    print("Hand it to the recipient out of band. They choose their own password, verify the address, then set up MFA.")
    if args.send_email:
        from app.services import notifications as notif
        row = notif.notify(notif.Message("EMAIL", inv.recipient_email, "Your RescueNet X invitation",
                                         f"You have been invited to RescueNet X as {inv.role}. Open this one-time link to activate your account "
                                         f"(it expires {inv.expires_at:%Y-%m-%d %H:%M} UTC):\n{link}\n", "INVITATION"))
        print(f"Email: transport {row.transport}, status {row.delivery_status}. "
              + ("Nothing was delivered to a mailbox." if row.transport != "SMTP" else "Accepted by the mail server; inbox delivery is not confirmed."))
    return 0


def list_invitations() -> int:
    ensure_schema(engine)
    db = SessionLocal()
    try:
        for inv in db.query(Invitation).order_by(Invitation.id.desc()).limit(100):
            print(f"#{inv.id:<4} {prov.invitation_status(inv):<9} {inv.role:<15} {inv.recipient_email:<30} agency={inv.agency_id} "
                  f"team={inv.team_id} expires {inv.expires_at:%Y-%m-%d %H:%M}Z by {inv.created_by}")
        return 0
    finally:
        db.close()


def revoke_invitation(db, actor, args) -> int:
    inv = db.get(Invitation, args.id)
    if inv is None:
        print("Refused: no such invitation.", file=sys.stderr)
        return 1
    done = prov.revoke(db, inv, actor, "HOST_OPERATOR")
    db.commit()
    print("Revoked." if done else f"Nothing to do: the invitation is {prov.invitation_status(inv)}.")
    return 0


def waive_contact_verification(db, user, username, actor, args) -> int:
    if user is None:
        print(f"Refused: no account named '{username}'.", file=sys.stderr)
        return 1
    user.contact_verification_waived_at = prov._now()
    record_audit(db, actor, "ACCOUNT_CLI_CONTACT_VERIFICATION_WAIVED", "user", user.id,
                 f"{username} ({user.role}); email {'present, NOT verified' if user.email else 'absent'}; reason: {args.reason}"[:480], role="HOST_OPERATOR")
    db.commit()
    print(f"Contact verification waived for '{username}'. The address was NOT marked verified; MFA is still mandatory.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--username", required=True)
    c.add_argument("--role", required=True, choices=ROLES)
    c.add_argument("--full-name", required=True)
    c.add_argument("--team-id")
    c.add_argument("--email", help="REQUIRED for privileged roles: the address the owner must verify before any access")
    c.add_argument("--agency-id", type=int)
    iv = sub.add_parser("invite")
    iv.add_argument("--email", required=True)
    iv.add_argument("--role", required=True, choices=list(PRIVILEGED_ROLES))
    iv.add_argument("--agency-id", type=int)
    iv.add_argument("--team-id")
    iv.add_argument("--hours", type=int)
    iv.add_argument("--send-email", action="store_true")
    sub.add_parser("list-invitations")
    rv = sub.add_parser("revoke-invitation")
    rv.add_argument("--id", type=int, required=True)
    w = sub.add_parser("waive-contact-verification")
    w.add_argument("--username", required=True)
    r = sub.add_parser("reset-password")
    r.add_argument("--username", required=True)
    m = sub.add_parser("reset-mfa")
    m.add_argument("--username", required=True)
    m.add_argument("--identity-verified", required=True, help="how the owner's identity was re-verified (recorded)")
    for p in (r, m):
        p.add_argument("--second-authorizer", help="name of a second authorised operator, to override the 24 h combination rule")
    for p in (c, r, m, iv, rv, w):
        p.add_argument("--reason", required=True, help="why this is needed (recorded in the audit log)")
        p.add_argument("--i-am-authorized", action="store_true", help="confirm you are authorised to do this on this server")
    args = ap.parse_args()
    if args.cmd == "list-invitations":
        return list_invitations()
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
    username = (getattr(args, "username", None) or "").strip().lower()
    db = SessionLocal()
    try:
        if args.cmd == "invite":
            return invite(db, actor, args)
        if args.cmd == "revoke-invitation":
            return revoke_invitation(db, actor, args)
        user = db.query(User).filter(User.username == username).first()
        if args.cmd == "reset-mfa":
            return reset_mfa(db, user, username, actor, args)
        if args.cmd == "waive-contact-verification":
            return waive_contact_verification(db, user, username, actor, args)
        if args.cmd == "reset-password" and user is not None and user.role in PRIVILEGED_ROLES and recent_recovery(db, user, ("ACCOUNT_CLI_MFA_RESET",)):
            if not override_ok(args, actor):
                print(f"Refused: this privileged account's MFA was reset in the last {settings.RECOVERY_COMBINATION_HOURS} hours. "
                      "Resetting the password too would combine both recoveries; wait, or have a second authorised operator pass "
                      "--second-authorizer NAME.", file=sys.stderr)
                return 3
        password = one_time_password()
        if args.cmd == "create":
            if user is not None:
                print(f"Refused: username '{username}' already exists.", file=sys.stderr)
                return 1
            if args.role == "RESCUE_OFFICER" and not (args.team_id and db.query(RescueTeam).filter(RescueTeam.id == args.team_id).first()):
                print("Refused: a rescue officer needs an existing --team-id.", file=sys.stderr)
                return 1
            email = prov.ver.normalise_email(args.email) if args.email else None
            if args.role in PRIVILEGED_ROLES and not (email and prov.EMAIL_RE.match(email)):
                print("Refused: a privileged account needs --email (the owner must verify it before any access). "
                      "Prefer 'invite', where the owner chooses their own password.", file=sys.stderr)
                return 1
            if args.agency_id is not None and not db.get(Agency, args.agency_id):
                print("Refused: no such --agency-id.", file=sys.stderr)
                return 1
            user = User(username=username, full_name=args.full_name, role=args.role, team_id=args.team_id, email=email,
                        agency_id=args.agency_id, password_hash=hash_password(password), must_change_password=True,
                        contact_verification_required=args.role in PRIVILEGED_ROLES)
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
