"""Shared pytest setup.

The SQLite database file is not committed to the repository, so a fresh clone
has no tables. This file points the app at a throwaway database for the test
session and seeds it with the same data the app uses on start-up.
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_TEST_DB_DIR = tempfile.mkdtemp(prefix="rescuenet_test_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_TEST_DB_DIR) / 'test_rescuenet.db'}")


import uuid

import pytest


@pytest.fixture(autouse=True)
def _restore_rescue_fleet():
    """Dispatching now really deploys a team, so a test that dispatches would otherwise use up the shared
    seeded teams for every later test. Team statuses are put back after each test, and any team the test
    created is parked on STANDBY so it cannot be chosen by another test."""
    from app.db.session import SessionLocal
    from app.models.entities import RescueTeam

    db = SessionLocal()
    saved = {t.id: t.status for t in db.query(RescueTeam).all()}
    db.close()
    yield
    db = SessionLocal()
    for t in db.query(RescueTeam).all():
        t.status = saved.get(t.id, "STANDBY")
    db.commit()
    db.close()


def make_team(client, lat=12.9300, lon=77.6200, tag="test"):
    """Create a fresh AVAILABLE rescue team through the API and return its id."""
    r = client.post("/api/teams/", json=dict(
        name=f"Test team {tag}", callsign=f"T{uuid.uuid4().hex[:6]}", vehicle_type="boat", members_count=4,
        skills="water rescue", latitude=lat, longitude=lon, base_station="Test base", contact_number="100"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def pytest_configure(config):
    from app.db.init_db import init_db

    init_db()


def sign_in(client, username: str = "commander", portal: str = None):
    """Log a demo account in and set its token on the client. Returns the client."""
    portals = {"admin": "admin", "commander": "operations", "operator": "operations",
               "officer": "operations", "volunteer": "public", "citizen": "public"}
    r = client.post("/api/auth/login", json={
        "portal": portal or portals[username], "username": username, "password": "Rescue@2026"})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return client
