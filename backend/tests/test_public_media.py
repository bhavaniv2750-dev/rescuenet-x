"""S0 security regression tests: evidence photos and guest uploads.

Each test states the attack or abuse it closes. Photos must never be reachable without authorisation, uploads must be
validated by decoding (not by name or Content-Type), re-encoded without metadata, and bounded in size, count and rate.
"""

import io
import re
import struct
import zlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Incident, MediaAsset, User
from tests.conftest import sign_in

REPORT = dict(title="Water in street", description="Knee deep water outside the house", area="Hebbal, Bengaluru",
              latitude=13.03, longitude=77.59, severity="MODERATE", people_affected=2)


@pytest.fixture(autouse=True)
def _clean_media():
    """Each test starts with no evidence photos (the test database is shared, and abuse limits are per client)."""
    import shutil
    def wipe():
        db = SessionLocal()
        db.query(MediaAsset).delete()
        db.commit(); db.close()
        shutil.rmtree(settings.UPLOAD_DIR, ignore_errors=True)
    wipe()
    yield
    wipe()


def anon():
    return TestClient(app)


def png_bytes(size=(64, 48), color=(30, 90, 160), mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format="PNG")
    return buf.getvalue()


def jpeg_with_gps_exif():
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"            # Make
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (12.0, 58.0, 12.0), "E", (77.0, 35.0, 24.0)
    buf = io.BytesIO()
    Image.new("RGB", (80, 60), (200, 10, 10)).save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def upload(client, data, name="p.png", ctype="image/png"):
    return client.post("/api/incidents/upload-image", files={"file": (name, data, ctype)})


def report_with(client, urls, **extra):
    body = dict(REPORT, **extra)
    if urls:
        body["image_url"] = urls[0]
        body["image_urls"] = urls[1:]
    return client.post("/api/incidents/", json=body)


def stored_bytes(asset_id):
    return (settings.UPLOAD_DIR / f"{asset_id}.jpg").read_bytes()


# ---------------------------------------------------------------- access control: private, never public

def test_photo_is_not_reachable_without_signing_in():
    g = anon()
    up = upload(g, png_bytes()).json()
    inc = report_with(g, [up["image_url"]]).json()
    assert inc["image_url"] == up["image_url"]
    assert g.get(up["image_url"]).status_code == 401                       # the old public route returned the file
    assert g.get(f"{settings.API_V1_STR}/media/{'0' * 32}").status_code == 401   # same answer for ids that do not exist


def test_no_static_mount_exposes_the_upload_folder():
    from starlette.routing import Mount
    assert not [r for r in app.routes if isinstance(r, Mount)]
    up = upload(anon(), png_bytes()).json()
    for path in (f"/uploads/{up['asset_id']}.jpg", f"/api/uploads/{up['asset_id']}.jpg", f"/{up['asset_id']}.jpg"):
        assert anon().get(path).status_code == 404


def test_staff_can_view_but_unrelated_citizen_cannot():
    g = anon()
    up = upload(g, png_bytes()).json()
    report_with(g, [up["image_url"]])
    commander = sign_in(TestClient(app), "commander")
    r = commander.get(up["image_url"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "private, no-store" and r.headers["x-content-type-options"] == "nosniff"
    assert sign_in(TestClient(app), "citizen").get(up["image_url"]).status_code == 404   # not their report
    assert sign_in(TestClient(app), "volunteer").get(up["image_url"]).status_code == 404


def test_citizen_sees_only_their_own_report_photo():
    citizen = sign_in(TestClient(app), "citizen")
    up = upload(citizen, png_bytes()).json()
    inc = report_with(citizen, [up["image_url"]]).json()
    assert inc["photos_attached"] == 1
    assert citizen.get(up["image_url"]).status_code == 200
    assert sign_in(TestClient(app), "volunteer").get(up["image_url"]).status_code == 404


def test_responder_sees_evidence_only_for_incidents_assigned_to_their_team():
    g = anon()
    up = upload(g, png_bytes()).json()
    inc = report_with(g, [up["image_url"]]).json()
    officer = sign_in(TestClient(app), "officer")
    assert officer.get(up["image_url"]).status_code == 404        # not assigned to the officer's team
    db = SessionLocal()
    team = db.query(User).filter(User.username == "officer").first().team_id
    db.query(Incident).filter(Incident.id == inc["id"]).update({"assigned_team_id": team})
    db.commit(); db.close()
    assert officer.get(up["image_url"]).status_code == 200        # now it is
    db = SessionLocal()
    db.query(Incident).filter(Incident.id == inc["id"]).update({"assigned_team_id": "TEAM-OTHER"})
    db.commit(); db.close()
    assert officer.get(up["image_url"]).status_code == 404        # reassigned away: access ends with the assignment


def test_unattached_upload_is_visible_only_to_its_signed_in_uploader():
    citizen = sign_in(TestClient(app), "citizen")
    up = upload(citizen, png_bytes()).json()
    assert citizen.get(up["image_url"]).status_code == 200
    assert sign_in(TestClient(app), "commander").get(up["image_url"]).status_code == 404
    guest_up = upload(anon(), png_bytes()).json()
    assert sign_in(TestClient(app), "commander").get(guest_up["image_url"]).status_code == 404


def test_legacy_route_is_no_longer_public(tmp_path):
    name = "inc_legacy1234_old.jpg"
    (settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    (settings.UPLOAD_DIR / name).write_bytes(png_bytes())
    db = SessionLocal()
    db.add(Incident(id="INC-LEGACYX", title="t", description="d", area="a", latitude=1, longitude=1, severity="LOW",
                    people_affected=1, status="REPORTED", source="CITIZEN_REPORT", data_label="OBSERVED",
                    image_url=f"/api/incidents/uploads/{name}", reporter_user_id=-1))
    db.commit(); db.close()
    url = f"/api/incidents/uploads/{name}"
    assert anon().get(url).status_code == 401
    assert sign_in(TestClient(app), "citizen").get(url).status_code == 404
    assert sign_in(TestClient(app), "commander").get(url).status_code == 200
    assert sign_in(TestClient(app), "commander").get("/api/incidents/uploads/..%2F..%2Fbackend%2F.jwt_secret").status_code == 404


# ---------------------------------------------------------------- validation by decoding, safe re-encoding

def test_metadata_gps_and_camera_info_are_removed():
    raw = jpeg_with_gps_exif()
    assert Image.open(io.BytesIO(raw)).getexif().get_ifd(0x8825), "fixture must really contain GPS data"
    up = upload(anon(), raw, "gps.jpg", "image/jpeg").json()
    data = stored_bytes(up["asset_id"])
    img = Image.open(io.BytesIO(data))
    assert img.format == "JPEG" and len(img.getexif()) == 0 and not img.getexif().get_ifd(0x8825)
    assert b"SecretCameraMaker" not in data and b"Exif" not in data and b"GPS" not in data


def test_appended_payload_is_not_kept():
    raw = png_bytes() + b"<script>alert(1)</script><?php system($_GET['c']); ?>"
    up = upload(anon(), raw).json()
    data = stored_bytes(up["asset_id"])
    assert b"<script>" not in data and b"<?php" not in data


@pytest.mark.parametrize("name,data,ctype", [
    ("evil.png", b"<html><script>alert(1)</script></html>", "image/png"),            # HTML renamed to .png
    ("evil.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>", "image/png"),
    ("shell.php.jpg", b"<?php echo 1; ?>", "image/jpeg"),
    ("empty.png", b"", "image/png"),
    ("trunc.png", png_bytes()[:40], "image/png"),                                      # truncated
    ("text.jpg", b"just text", "image/jpeg"),
    ("real.pdf", b"%PDF-1.4\n%fake", "application/pdf"),
])
def test_files_that_are_not_photos_are_rejected(name, data, ctype):
    r = upload(anon(), data, name, ctype)
    assert r.status_code == 400, r.text
    db = SessionLocal()
    assert db.query(MediaAsset).count() == 0          # nothing registered
    db.close()


def test_rejected_upload_stores_nothing():
    before = len(list(settings.UPLOAD_DIR.glob("*"))) if settings.UPLOAD_DIR.exists() else 0
    assert upload(anon(), b"<html>x</html>", "a.png").status_code == 400
    after = len(list(settings.UPLOAD_DIR.glob("*"))) if settings.UPLOAD_DIR.exists() else 0
    assert after == before


def test_gif_and_animated_images_are_rejected():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buf, format="GIF")
    assert upload(anon(), buf.getvalue(), "a.gif", "image/gif").status_code == 400
    frames = [Image.new("RGB", (16, 16), (i * 40, 0, 0)) for i in range(4)]
    buf = io.BytesIO()
    frames[0].save(buf, format="WEBP", save_all=True, append_images=frames[1:], duration=100)
    assert upload(anon(), buf.getvalue(), "a.webp", "image/webp").status_code == 400


def test_decompression_bomb_is_rejected_cheaply():
    # a tiny PNG header that declares a 40,000 x 40,000 image
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 40000, 40000, 8, 0, 0, 0, 0)
    raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00" * 100)) + chunk(b"IEND", b"")
    r = upload(anon(), raw)
    assert r.status_code == 400 and ("large" in r.json()["detail"].lower() or "valid" in r.json()["detail"].lower())


def test_oversized_file_is_rejected_before_decoding():
    r = upload(anon(), b"\xff\xd8\xff" + b"0" * (settings.MAX_IMAGE_BYTES + 10), "big.jpg", "image/jpeg")
    assert r.status_code == 400 and "5 MB" in r.json()["detail"]


def test_large_photo_is_downscaled_and_traversal_filename_is_ignored():
    big = Image.new("RGB", (4000, 3000), (10, 120, 200))
    buf = io.BytesIO(); big.save(buf, format="JPEG")
    up = upload(anon(), buf.getvalue(), "../../../etc/passwd.jpg", "image/jpeg").json()
    assert re.fullmatch(r"[0-9a-f]{32}", up["asset_id"])
    img = Image.open(io.BytesIO(stored_bytes(up["asset_id"])))
    assert max(img.size) <= settings.IMAGE_MAX_SIDE_PX
    assert not (settings.UPLOAD_DIR.parent / "passwd.jpg").exists()


def test_transparent_png_is_flattened():
    up = upload(anon(), png_bytes(color=(255, 0, 0, 0), mode="RGBA")).json()
    assert Image.open(io.BytesIO(stored_bytes(up["asset_id"]))).mode == "RGB"


# ---------------------------------------------------------------- attaching photos to reports

def test_cannot_attach_another_reports_photo_or_an_external_url():
    g = anon()
    up = upload(g, png_bytes()).json()
    first = report_with(g, [up["image_url"]]).json()
    assert first["photos_attached"] == 1
    reuse = report_with(g, [up["image_url"]]).json()
    assert reuse["photos_attached"] == 0 and reuse["image_url"] is None and reuse["photo_warnings"]
    ext = report_with(g, ["http://evil.example/x.jpg"]).json()
    assert ext["image_url"] is None and ext["photos_attached"] == 0
    js = report_with(g, ["javascript:alert(1)"]).json()
    assert js["image_url"] is None


def test_signed_in_users_photo_cannot_be_attached_by_someone_else():
    citizen = sign_in(TestClient(app), "citizen")
    up = upload(citizen, png_bytes()).json()
    other = report_with(anon(), [up["image_url"]]).json()
    assert other["photos_attached"] == 0


def test_expired_unattached_upload_cannot_be_attached():
    g = anon()
    up = upload(g, png_bytes()).json()
    db = SessionLocal()
    from datetime import timedelta
    from app.services.media import now_utc
    db.query(MediaAsset).filter(MediaAsset.id == up["asset_id"]).update({"created_at": now_utc() - timedelta(minutes=90)})
    db.commit(); db.close()
    assert report_with(g, [up["image_url"]]).json()["photos_attached"] == 0


def test_at_most_five_photos_per_report_and_report_still_saved():
    g = anon()
    urls = [upload(g, png_bytes(color=(i, i, i))).json()["image_url"] for i in range(6)]
    r = report_with(g, urls)
    assert r.status_code == 201
    body = r.json()
    assert body["photos_attached"] == 5 and body["photo_warnings"]
    assert anon().post("/api/incidents/", json=dict(REPORT, image_urls=urls + urls)).status_code == 422  # schema cap


def test_photo_problem_never_blocks_an_emergency_report():
    r = report_with(anon(), ["/api/media/" + "a" * 32])
    assert r.status_code == 201 and r.json()["photos_attached"] == 0


# ---------------------------------------------------------------- abuse controls

def test_guest_upload_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "GUEST_UPLOADS_PER_HOUR", 3)
    g = anon()
    assert [upload(g, png_bytes(color=(i, 0, 0))).status_code for i in range(3)] == [201, 201, 201]
    r = upload(g, png_bytes())
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0 and "112" in r.json()["detail"]


def test_storage_quota_blocks_photos_but_not_reports(monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_QUOTA_MB", 0)
    g = anon()
    r = upload(g, png_bytes())
    assert r.status_code == 400 and "storage is full" in r.json()["detail"]
    assert report_with(g, []).status_code == 201


def test_guest_daily_upload_quota(monkeypatch):
    monkeypatch.setattr(settings, "GUEST_UPLOAD_MB_PER_DAY", 0)
    r = upload(anon(), png_bytes())
    assert r.status_code == 400 and "Daily photo upload limit" in r.json()["detail"]
    assert upload(sign_in(TestClient(app), "citizen"), png_bytes()).status_code == 201   # the daily guest quota is for guests


def test_unattached_upload_cap_per_client(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UNATTACHED_UPLOADS_PER_CLIENT", 2)
    g = anon()
    assert upload(g, png_bytes(color=(1, 1, 1))).status_code == 201
    assert upload(g, png_bytes(color=(2, 2, 2))).status_code == 201
    assert upload(g, png_bytes(color=(3, 3, 3))).status_code == 400


def test_abandoned_uploads_are_purged_but_attached_evidence_never_is():
    from datetime import timedelta
    from app.services.media import now_utc
    g = anon()
    abandoned = upload(g, png_bytes(color=(9, 9, 9))).json()
    kept = upload(g, png_bytes(color=(8, 8, 8))).json()
    report_with(g, [kept["image_url"]])
    old = now_utc() - timedelta(days=3)
    db = SessionLocal()
    db.query(MediaAsset).filter(MediaAsset.id.in_([abandoned["asset_id"], kept["asset_id"]])).update({"created_at": old})
    db.commit(); db.close()
    upload(g, png_bytes(color=(7, 7, 7)))                       # triggers the purge
    assert not (settings.UPLOAD_DIR / f"{abandoned['asset_id']}.jpg").exists()
    assert (settings.UPLOAD_DIR / f"{kept['asset_id']}.jpg").exists()


# ---------------------------------------------------------------- legacy photos

def test_legacy_import_is_dry_by_default_and_never_deletes_originals():
    from app.services.media import import_legacy_uploads
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (settings.UPLOAD_DIR / "inc_aaaaaaaaaa_good.png").write_bytes(png_bytes())
    (settings.UPLOAD_DIR / "inc_bbbbbbbbbb_bad.png").write_bytes(b"<html>not an image</html>")
    db = SessionLocal()
    db.query(Incident).filter(Incident.image_url.like("/api/incidents/uploads/%")).delete(synchronize_session=False)  # other tests' leftovers
    db.commit()
    for iid, fn in (("INC-LEGGOOD", "inc_aaaaaaaaaa_good.png"), ("INC-LEGBAD", "inc_bbbbbbbbbb_bad.png"), ("INC-LEGGONE", "inc_missing.png")):
        db.add(Incident(id=iid, title="t", description="d", area="a", latitude=1, longitude=1, severity="LOW", people_affected=1,
                        status="REPORTED", source="CITIZEN_REPORT", data_label="OBSERVED", image_url=f"/api/incidents/uploads/{fn}"))
    db.commit()

    dry = import_legacy_uploads(db, apply=False)
    assert (dry["found"], dry["importable"], dry["imported"]) == (3, 1, 0)
    assert db.get(Incident, "INC-LEGGOOD").image_url.startswith("/api/incidents/uploads/")

    done = import_legacy_uploads(db, apply=True)
    assert done["imported"] == 1 and done["rejected"] == ["INC-LEGBAD"] and done["missing_file"] == ["INC-LEGGONE"]
    inc = db.get(Incident, "INC-LEGGOOD")
    assert inc.image_url.startswith("/api/media/")
    asset = db.query(MediaAsset).filter(MediaAsset.incident_id == "INC-LEGGOOD").one()
    assert asset.legacy_source == "/api/incidents/uploads/inc_aaaaaaaaaa_good.png"          # reversible
    assert (settings.UPLOAD_DIR / "inc_aaaaaaaaaa_good.png").exists()                       # original kept
    assert db.get(Incident, "INC-LEGBAD").image_url.endswith("inc_bbbbbbbbbb_bad.png")  # untouched
    db.close()
    assert sign_in(TestClient(app), "commander").get(inc.image_url).status_code == 200
    assert anon().get(inc.image_url).status_code == 401
