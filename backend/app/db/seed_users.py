"""Create the first accounts.

* With SEED_DEMO_USERS on AND RESCUENET_ENV=development (never in production),
  one account per role is created with DEMO_USER_PASSWORD.
* With it off, only an admin account is created, using RESCUENET_ADMIN_PASSWORD
  or a random password that is printed once and saved to backend/.admin_password.
Nothing is created if any user already exists.
"""

import secrets
from pathlib import Path

from app.core.config import BASE_DIR, settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.entities import RescueTeam, User, Volunteer

DEMO_ACCOUNTS = [
    # username, full name, role, team, volunteer, email
    ("admin", "System Administrator", "ADMIN", None, None, "admin@rescuenet.local"),
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
        if settings.SEED_DEMO_USERS and not settings.is_development:
            print("[init_db] SEED_DEMO_USERS is ignored because RESCUENET_ENV is not 'development'. "
                  "Demo accounts are never created in production.")
        if settings.SEED_DEMO_USERS and settings.is_development:
            pw_hash = hash_password(settings.DEMO_USER_PASSWORD)
            for username, name, role, team, vol, email in DEMO_ACCOUNTS:
                if team and not db.query(RescueTeam).filter(RescueTeam.id == team).first():
                    team = db.query(RescueTeam.id).order_by(RescueTeam.id).scalar()
                if vol and not db.query(Volunteer).filter(Volunteer.id == vol).first():
                    vol = None
                db.add(User(username=username, full_name=name, role=role, email=email,
                            password_hash=pw_hash, team_id=team, volunteer_id=vol))
            db.commit()
            print(f"[init_db] Created demo accounts ({', '.join(a[0] for a in DEMO_ACCOUNTS)}) "
                  f"with the DEMO_USER_PASSWORD. Set SEED_DEMO_USERS=false for a real deployment.")
            return
        password = settings.ADMIN_PASSWORD or secrets.token_urlsafe(12)
        db.add(User(username="admin", full_name="System Administrator", role="ADMIN",
                    password_hash=hash_password(password)))
        db.commit()
        if not settings.ADMIN_PASSWORD:
            path = Path(BASE_DIR) / "backend" / ".admin_password"
            try:
                path.write_text(password + "\n")
            except OSError:
                pass
            print(f"[init_db] Created admin account. Username: admin  Password: {password}  (also in {path})")
    finally:
        db.close()
