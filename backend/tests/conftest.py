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
