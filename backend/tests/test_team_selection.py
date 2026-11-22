"""Unit tests for the team-ranking module and the migration that adds the original-risk columns."""

import math
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from app.db.migrate import upgrade_schema
from app.services.team_selection import (
    TIE_TOLERANCE_KM,
    haversine_km_exact,
    rank_available_teams,
    select_team,
    valid_coordinates,
)


def team(tid, lat, lon, status="AVAILABLE"):
    return SimpleNamespace(id=tid, name=tid, latitude=lat, longitude=lon, status=status)


def test_haversine_matches_known_distances():
    assert haversine_km_exact(12.97, 77.59, 12.97, 77.59) == 0.0
    # One degree of latitude (or of longitude on the equator) is about 111.19 km on a 6371.0088 km sphere.
    assert haversine_km_exact(10.0, 77.0, 11.0, 77.0) == pytest.approx(111.195, abs=0.01)
    assert haversine_km_exact(0.5, 10.0, 0.5, 11.0) == pytest.approx(111.19 * math.cos(math.radians(0.5)), abs=0.05)
    # Bengaluru to Mysuru is roughly 128 km as the crow flies.
    assert 120 < haversine_km_exact(12.9716, 77.5946, 12.2958, 76.6394) < 135
    assert haversine_km_exact(12.9, 77.6, 13.1, 77.7) == pytest.approx(haversine_km_exact(13.1, 77.7, 12.9, 77.6))


@pytest.mark.parametrize("lat,lon,ok", [
    (12.97, 77.59, True), (-90, 180, True), (91, 0, False), (0, 181, False),
    (None, 77.0, False), (12.0, None, False), ("abc", 77.0, False), (float("nan"), 77.0, False),
    (float("inf"), 77.0, False), (0.0, 0.0, False), ("12.5", "77.5", True),
])
def test_coordinate_validation(lat, lon, ok):
    assert valid_coordinates(lat, lon) is ok


def test_ranking_is_nearest_first_and_explains_every_skipped_team():
    ranked, skipped = rank_available_teams(
        [team("far", 13.3, 77.6), team("near", 12.931, 77.621), team("busy", 12.9301, 77.6201, "DEPLOYED"),
         team("bad", None, 77.6), team("mid", 13.0, 77.65)], 12.93, 77.62)
    assert [r.team.id for r in ranked] == ["near", "mid", "far"]
    assert [r.distance_km for r in ranked] == sorted(r.distance_km for r in ranked)
    assert len(skipped) == 2 and any("busy" in n and "DEPLOYED" in n for n in skipped) and any("bad" in n for n in skipped)


def test_status_comparison_ignores_case_and_a_team_without_status_is_not_available():
    assert [r.team.id for r in rank_available_teams([team("a", 12.9, 77.6, "available")], 12.93, 77.62)[0]] == ["a"]
    assert rank_available_teams([team("a", 12.9, 77.6, None)], 12.93, 77.62)[0] == []


def test_ties_are_broken_by_team_id_so_results_repeat():
    same_spot = [team("T-B", 12.9, 77.6), team("T-A", 12.9, 77.6)]
    assert [select_team(list(reversed(same_spot)), 12.93, 77.62).team.id for _ in range(3)] == ["T-A"] * 3
    assert select_team(same_spot, 12.93, 77.62).team.id == "T-A"


def test_a_suggestion_inside_the_tolerance_is_accepted_and_outside_it_is_overridden():
    near = team("near", 12.93, 77.62)
    almost = team("almost", 12.93 + 0.0002, 77.62)  # ~22 m farther, inside the 50 m tolerance
    far = team("far", 13.2, 77.62)
    assert TIE_TOLERANCE_KM == 0.05
    assert select_team([near, almost, far], 12.93, 77.62, preferred_id="almost").team.id == "almost"
    out = select_team([near, almost, far], 12.93, 77.62, preferred_id="far")
    assert out.team.id == "near" and any(n.startswith("Overrode suggested team 'far'") for n in out.notes)


def test_no_choice_without_valid_incident_coordinates_or_available_teams():
    assert select_team([team("a", 12.9, 77.6)], None, 77.62).team is None
    assert select_team([team("a", 12.9, 77.6)], 12.93, float("nan")).team is None
    empty = select_team([team("a", 12.9, 77.6, "STANDBY")], 12.93, 77.62, preferred_id="a")
    assert empty.team is None and any("REJECTED" in n for n in empty.notes)


def test_migration_backfills_the_original_risk_and_is_repeatable():
    db_file = Path(tempfile.mkdtemp(prefix="mig_")) / "old.db"
    engine = create_engine(f"sqlite:///{db_file}")
    with engine.begin() as c:  # a database made before the original-risk columns existed
        c.execute(text("CREATE TABLE incidents (id TEXT PRIMARY KEY, severity TEXT, people_affected INTEGER, status TEXT)"))
        c.execute(text("INSERT INTO incidents VALUES ('INC-1', 'CRITICAL', 9, 'ASSIGNED'), ('INC-2', 'LOW', 1, 'REPORTED')"))
    added = upgrade_schema(engine)
    assert {"incidents.reported_severity", "incidents.reported_people_affected", "incidents.risk_downgraded_by"} <= set(added)
    with engine.connect() as c:
        rows = {r[0]: r[1:] for r in c.execute(text("SELECT id, reported_severity, reported_people_affected, status FROM incidents"))}
    assert rows["INC-1"] == ("CRITICAL", 9, "DISPATCHED")  # backfilled; legacy status also mapped
    assert rows["INC-2"] == ("LOW", 1, "REPORTED")
    assert not [a for a in upgrade_schema(engine) if a.startswith("incidents.reported")]  # second run changes nothing
