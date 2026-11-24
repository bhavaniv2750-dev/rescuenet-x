"""Development fixtures: simulated demo accounts (S5).

Production NEVER creates an account here. The first administrator is created by a person with shell access to the server
(scripts/bootstrap_admin.py), further privileged accounts by invitation (scripts/account_admin.py invite), citizens and
volunteers register themselves.

Demo accounts are created only when ALL of these hold: the database has no users, RESCUENET_ENV=development, and
SEED_DEMO_USERS=true was set explicitly (it is OFF by default). There is no built-in password: the password is
DEMO_USER_PASSWORD from the environment if you set one, otherwise a random one printed ONCE to this console and stored nowhere
in clear. Every fixture account is flagged `is_demo`, is labelled "(Demo)" / simulated, and privileged ones still must enrol MFA.
"""

import secrets

from app.core.config import settings
from app.core.security import hash_password, password_problem
from app.db.session import SessionLocal
from app.models.entities import RescueTeam, User, Volunteer

DEMO_ACCOUNTS = [
    # username, full name, role, team, volunteer, email
    ("admin", "System Administrator (Demo)", "ADMIN", None, None, "admin@rescuenet.local"),
    ("developer", "Developer (Demo, diagnostics only)", "DEVELOPER", None, None, "developer@rescuenet.local"),
    ("commander", "Incident Commander (Demo)", "COMMANDER", None, None, "commander@rescuenet.local"),
    ("operator", "Control Room Operator (Demo)", "OPERATOR", None, None, "operator@rescuenet.local"),
    ("officer", "Rescue Officer, Thunder-1 (Demo)", "RESCUE_OFFICER", "TEAM-NDRF-10", None, "officer@rescuenet.local"),
    ("volunteer", "Vikram Rao (Demo Volunteer)", "VOLUNTEER", None, "VOL-101", "vikram.rao@rescue.net"),
    ("citizen", "Citizen Reporter (Demo)", "CITIZEN", None, None, "citizen@rescuenet.local"),
]


def seed_users() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        if settings.is_production or not settings.SEED_DEMO_USERS:
            print("[init_db] No accounts exist. Create the first administrator on this server with "
                  "'python scripts/bootstrap_admin.py --help' (see docs/security/S5_ACCOUNTS_AGENCIES.md).")
            return
        password, generated = settings.DEMO_USER_PASSWORD, False
        if password and password_problem(password):
            print(f"[init_db] DEMO_USER_PASSWORD is not acceptable ({password_problem(password)}); using a random one instead.")
            password = ""
        if not password:
            password, generated = secrets.token_urlsafe(14), True
        pw_hash = hash_password(password)
        for username, name, role, team, vol, email in DEMO_ACCOUNTS:
            if team and not db.query(RescueTeam).filter(RescueTeam.id == team).first():
                team = db.query(RescueTeam.id).order_by(RescueTeam.id).scalar()
            if vol and not db.query(Volunteer).filter(Volunteer.id == vol).first():
                vol = None
            db.add(User(username=username, full_name=name, role=role, email=email, password_hash=pw_hash,
                        team_id=team, volunteer_id=vol, is_demo=True))
        db.commit()
        print(f"[init_db] DEVELOPMENT FIXTURES: created simulated demo accounts ({', '.join(a[0] for a in DEMO_ACCOUNTS)}).")
        if generated:
            print(f"[init_db] Their shared password (shown once, stored nowhere in clear): {password}")
        else:
            print("[init_db] Their password is the DEMO_USER_PASSWORD you set.")
    finally:
        db.close()
