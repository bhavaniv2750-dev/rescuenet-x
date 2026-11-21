"""Flood photo analysis. Inference tests are skipped when the model weights are not downloaded."""

import io

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from tests.conftest import sign_in
from app.services.vision_service import flood_vision_service

client = sign_in(TestClient(app), "commander")
needs_model = pytest.mark.skipif(not flood_vision_service.status()["ready"], reason="vision weights not downloaded")


def _first_flood_photo():
    return sorted(p for p in settings.FLOOD_IMG_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})[0]


def test_status_endpoint_reports_model_state():
    body = client.get("/api/vision/status").json()
    assert {"ready", "weights_present", "runtime_installed"} <= body.keys()


def test_rejects_non_image_upload():
    r = client.post("/api/vision/analyze", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_dataset_path_traversal_blocked():
    assert client.get("/api/vision/dataset/..%2F..%2Fetc%2Fpasswd").status_code in (400, 404)


@needs_model
def test_flood_photo_is_detected_and_labelled_predicted():
    photo = _first_flood_photo()
    r = client.get(f"/api/vision/dataset/{photo.name}", params={"overlay": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data_label"] == "PREDICTED"
    assert 0.0 <= body["flood_probability"] <= 1.0
    assert body["water_depth"]["estimated"] is False
    assert body["suggested_severity"] in {"LOW", "MODERATE", "HIGH", "CRITICAL"}


@needs_model
def test_plain_grey_image_is_not_a_flood():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (320, 240), (128, 128, 128)).save(buf, format="PNG")
    r = client.post("/api/vision/analyze", files={"file": ("grey.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200
    assert r.json()["water_coverage_pct"] < 5


@needs_model
def test_incident_photo_analysis_is_stored():
    photo = _first_flood_photo()
    up = client.post("/api/incidents/upload-image", files={"file": (photo.name, photo.read_bytes(), "image/jpeg")}).json()
    inc = client.post("/api/incidents/", json={
        "title": "Photo test", "description": "Street under water", "area": "Hebbal",
        "latitude": 13.03, "longitude": 77.59, "severity": "MODERATE", "people_affected": 1,
        "image_url": up["image_url"], "reported_water_depth": "knee",
    }).json()
    assert inc["reported_water_depth"] == "KNEE"
    r = client.post(f"/api/incidents/{inc['id']}/analyze-photo")
    assert r.status_code == 200, r.text
    assert r.json()["photo_analysis"]["data_label"] == "PREDICTED"
    (settings.UPLOAD_DIR / up["filename"]).unlink(missing_ok=True)
