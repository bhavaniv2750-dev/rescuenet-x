"""S2: the old long-lived (480-minute, session-less) JWTs are invalid the moment the new session system is active.
There is NO grace period: they are refused on every authenticated endpoint, for every role, even with a valid signature."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.security import ALGORITHM, jwt_secret
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import User
from tests.conftest import sign_in
from tests.test_endpoint_authorization import ANON_ONLY, MUST_ALLOW, PLACEHOLDERS, PUBLIC, probe

DEMO = ["admin", "developer", "commander", "operator", "officer", "volunteer", "citizen"]


def legacy_token(user_id, role, minutes=480):
    """Exactly what the pre-S2 code issued: HS256, same secret, claims sub/role/iat/exp, no session id, 480 minutes."""
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(minutes=minutes)}, jwt_secret(), algorithm=ALGORITHM)


def users():
    db = SessionLocal()
    try:
        return [(u.id, u.role, u.username) for u in db.query(User).filter(User.username.in_(DEMO)).all()]
    finally:
        db.close()


@pytest.mark.parametrize("uid,role,name", users())
def test_a_legacy_token_with_a_valid_signature_is_refused_on_every_protected_endpoint(uid, role, name):
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {legacy_token(uid, role)}"
    checked = 0
    for (method, path), allowed in MUST_ALLOW.items():
        if allowed == PUBLIC or (method, path) in ANON_ONLY and False:
            continue
        got = probe(c, method, path)
        assert got == "401", f"{method} {path} accepted a legacy token for {name} ({got})"
        checked += 1
    assert checked >= 40


def test_the_legacy_refusal_message_tells_people_to_sign_in_again():
    uid, role, _ = users()[0]
    r = TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {legacy_token(uid, role)}"})
    assert r.status_code == 401 and "invalid access token" in r.json()["detail"].lower()
    assert r.headers["www-authenticate"] == "Bearer"


def test_a_legacy_token_cannot_be_exchanged_for_a_session():
    uid, role, _ = users()[0]
    c = TestClient(app)
    assert c.post("/api/auth/refresh", headers={"Authorization": f"Bearer {legacy_token(uid, role)}", "X-CSRF-Token": "x"}).status_code == 401


def test_even_a_freshly_minted_legacy_token_is_refused_so_there_is_no_grace_window():
    uid, role, _ = users()[0]
    r = TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {legacy_token(uid, role, minutes=1)}"})
    assert r.status_code == 401


def test_legacy_tokens_do_not_block_guest_emergency_reporting():
    uid, role, _ = users()[0]
    r = TestClient(app).post("/api/public/reports", headers={"Authorization": f"Bearer {legacy_token(uid, role)}"}, json=dict(
        title="Flooding", description="Water rising in lane", area="Hebbal", latitude=13.0, longitude=77.6, severity="LOW", people_affected=1))
    assert r.status_code == 201


def test_people_signed_in_again_after_the_cut_over_work_normally():
    assert sign_in(TestClient(app), "commander").get("/api/auth/me").status_code == 200
