"""S0 security regression tests: guest reporting and public tracking references.

Guest reporting must keep working without an account, the public identifiers must be random and non-enumerable,
the tracking code must be stored only as a hash, and brute-force attempts must be throttled.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Incident
from app.services import public_refs
from tests.conftest import sign_in

REPORT = dict(title="Water entering homes", description="Lane is flooded, elderly residents inside", area="Bellandur, Bengaluru",
              latitude=12.93, longitude=77.67, severity="HIGH", people_affected=4,
              reporter_name="Private Person", reporter_contact="+91-90000-00000")
REF_RE = re.compile(r"^RN-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$")
CODE_RE = re.compile(r"^([0-9A-HJKMNP-TV-Z]{4}-){4}[0-9A-HJKMNP-TV-Z]{4}$")


def anon():
    return TestClient(app)


def submit(client=None, **over):
    return (client or anon()).post("/api/public/reports", json=dict(REPORT, **over))


def track(client, ref, code):
    h = {"X-Tracking-Code": code} if code is not None else {}
    return client.get(f"/api/public/reports/{ref}", headers=h)


# ---------------------------------------------------------------- guest reporting stays open

def test_guest_can_report_without_any_account():
    r = submit()
    assert r.status_code == 201, r.text
    body = r.json()
    assert REF_RE.match(body["public_ref"]) and CODE_RE.match(body["tracking_code"])
    assert body["status"] == "Received" and "112" in body["notice"]


def test_legacy_endpoint_still_accepts_guests_and_returns_tracking_details():
    r = anon().post("/api/incidents/", json=REPORT)
    assert r.status_code == 201
    body = r.json()
    assert REF_RE.match(body["public_ref"]) and CODE_RE.match(body["tracking_code"])


def test_public_response_never_contains_internal_id_or_private_fields():
    body = submit().json()
    assert set(body) == {"public_ref", "tracking_code", "status", "received_at", "photos_attached", "photo_warnings", "notice"}
    assert "INC-" not in str(body) and "Private Person" not in str(body)


def test_report_validation_still_gives_a_clear_error():
    r = anon().post("/api/public/reports", json={"title": "x"})
    assert r.status_code == 422


# ---------------------------------------------------------------- identifiers are random and non-enumerable

def test_internal_ids_are_random_not_sequential():
    ids = [anon().post("/api/incidents/", json=REPORT).json()["id"] for _ in range(4)]
    assert all(re.fullmatch(r"INC-[0-9A-Z]{8}", i) for i in ids)
    assert len(set(ids)) == 4
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    nums = [sum(alphabet.index(ch) * 32 ** k for k, ch in enumerate(reversed(i[4:]))) for i in ids]
    assert sorted(nums) != list(range(min(nums), min(nums) + 4))   # not consecutive counter values


def test_references_and_codes_are_unique_and_high_entropy():
    refs = {public_refs.new_public_ref() for _ in range(3000)}
    codes = {public_refs.new_tracking_code() for _ in range(3000)}
    assert len(refs) == 3000 and len(codes) == 3000
    assert all(REF_RE.match(r) for r in refs) and all(CODE_RE.match(c) for c in codes)
    # 12 and 20 symbols of a 32-letter alphabet = 60 and 100 random bits
    assert 32 ** 12 >= 2 ** 60 and 32 ** 20 >= 2 ** 100


def test_tracking_code_is_stored_only_as_a_hash():
    body = submit().json()
    db = SessionLocal()
    row = db.query(Incident).filter(Incident.public_ref == body["public_ref"]).one()
    stored = row.tracking_code_hash
    dump = " ".join(str(getattr(row, c.name)) for c in Incident.__table__.columns)
    db.close()
    raw = public_refs.normalise(body["tracking_code"])
    assert len(stored) == 64 and stored != body["tracking_code"] and raw not in dump
    assert stored == public_refs.hash_code(body["tracking_code"])


def test_nothing_public_looks_up_a_report_by_internal_id():
    created = anon().post("/api/incidents/", json=REPORT).json()
    g = anon()
    assert g.get(f"/api/incidents/{created['id']}").status_code == 401
    assert g.get("/api/incidents/").status_code == 401
    assert g.get(f"/api/public/reports/{created['id']}", headers={"X-Tracking-Code": created["tracking_code"]}).status_code == 404


# ---------------------------------------------------------------- tracking

def test_tracking_with_correct_code_returns_only_limited_fields():
    body = submit().json()
    r = track(anon(), body["public_ref"], body["tracking_code"])
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"public_ref", "status", "received_at", "updated_at", "photo_count", "notice"}
    text = str(data)
    for secret in ("Private Person", "+91-90000", "Bellandur", "INC-", "12.93", "assigned"):
        assert secret not in text


def test_tracking_accepts_lowercase_and_spaces():
    body = submit().json()
    sloppy = body["tracking_code"].lower().replace("-", " ")
    assert track(anon(), body["public_ref"].lower(), sloppy).status_code == 200


def test_wrong_code_unknown_ref_and_missing_code_look_identical():
    body = submit().json()
    wrong = track(anon(), body["public_ref"], "0000-0000-0000-0000-0000")
    unknown = track(anon(), "RN-0000-0000-0000", "0000-0000-0000-0000-0000")
    missing = track(anon(), body["public_ref"], None)
    garbage = track(anon(), "not a ref", "x")
    assert {r.status_code for r in (wrong, unknown, missing, garbage)} == {404}
    assert wrong.json() == unknown.json() == missing.json() == garbage.json()


def test_legacy_reports_without_tracking_code_cannot_be_tracked():
    db = SessionLocal()
    db.add(Incident(id="INC-OLDREPORT", title="t", description="d", area="a", latitude=1, longitude=1, severity="LOW",
                    people_affected=1, status="REPORTED", source="CITIZEN_REPORT", data_label="OBSERVED",
                    public_ref="RN-AAAA-BBBB-CCCC", tracking_code_hash=None))
    db.commit(); db.close()
    assert track(anon(), "RN-AAAA-BBBB-CCCC", "").status_code == 404
    assert track(anon(), "RN-AAAA-BBBB-CCCC", "0000-0000-0000-0000-0000").status_code == 404
    assert public_refs.code_matches("", None) is False and public_refs.code_matches("anything", None) is False


def test_status_is_plain_language_and_follows_the_incident():
    body = submit().json()
    db = SessionLocal()
    for internal, expected in (("VERIFIED", "Being assessed"), ("DISPATCHED", "A rescue team has been assigned"),
                               ("ON_SCENE", "Responders are at the location"), ("RESOLVED", "Resolved")):
        db.query(Incident).filter(Incident.public_ref == body["public_ref"]).update({"status": internal})
        db.commit()
        assert track(anon(), body["public_ref"], body["tracking_code"]).json()["status"] == expected
    db.close()


def test_brute_force_guessing_is_throttled(monkeypatch):
    monkeypatch.setattr(settings, "TRACKING_FAILURES_PER_15_MIN", 5)
    body = submit().json()
    g = anon()
    codes = [track(g, body["public_ref"], f"{i:04d}-0000-0000-0000-0000").status_code for i in range(5)]
    assert codes == [404] * 5
    blocked = track(g, body["public_ref"], "1111-1111-1111-1111-1111")
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
    # even the right code is refused during the lock-out, so guessing cannot be told apart from success
    assert track(g, body["public_ref"], body["tracking_code"]).status_code == 429


def test_lookup_volume_is_limited(monkeypatch):
    monkeypatch.setattr(settings, "TRACKING_LOOKUPS_PER_HOUR", 3)
    body = submit().json()
    g = anon()
    assert [track(g, body["public_ref"], body["tracking_code"]).status_code for _ in range(3)] == [200] * 3
    assert track(g, body["public_ref"], body["tracking_code"]).status_code == 429


# ---------------------------------------------------------------- abuse limits on reporting

def test_guest_report_limit_is_ten_per_hour_with_an_emergency_note():
    g = anon()
    assert settings.GUEST_REPORTS_PER_HOUR == 10
    assert [submit(g).status_code for _ in range(10)] == [201] * 10
    r = submit(g)
    assert r.status_code == 429 and "112" in r.json()["detail"] and int(r.headers["retry-after"]) > 0
    assert anon().post("/api/incidents/", json=REPORT).status_code == 429       # same limit on the legacy endpoint


def test_forged_forwarded_header_does_not_bypass_the_limit():
    g = anon()
    for i in range(10):
        assert g.post("/api/public/reports", json=REPORT, headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code == 201
    assert g.post("/api/public/reports", json=REPORT, headers={"X-Forwarded-For": "10.9.9.9"}).status_code == 429


def test_behind_a_trusted_proxy_each_client_has_its_own_limit(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    g = anon()
    for _ in range(10):
        assert g.post("/api/public/reports", json=REPORT, headers={"X-Forwarded-For": "203.0.113.5"}).status_code == 201
    assert g.post("/api/public/reports", json=REPORT, headers={"X-Forwarded-For": "203.0.113.5"}).status_code == 429
    assert g.post("/api/public/reports", json=REPORT, headers={"X-Forwarded-For": "203.0.113.6"}).status_code == 201


def test_signed_in_users_are_not_held_to_the_guest_limit_and_reports_are_linked():
    c = sign_in(TestClient(app), "citizen")
    assert [c.post("/api/public/reports", json=REPORT).status_code for _ in range(12)] == [201] * 12
    mine = c.get("/api/incidents/mine").json()["items"]
    assert mine and all(i["public_ref"] for i in mine)


def test_staff_view_includes_public_ref_for_support_calls():
    submit()
    items = sign_in(TestClient(app), "commander").get("/api/incidents/").json()["items"]
    assert any(i.get("public_ref") for i in items)
