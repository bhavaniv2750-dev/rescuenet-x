"""Regression tests for the three P0 safety defects found in the agent audit.

G5  Commander-approval bypass: an operator could lower severity / people_affected, then dispatch.
D4  Dispatch without an assigned team: an incident could be marked DISPATCHED with nobody sent,
    and a team could be double-booked.
D1  Wrong nearest-team selection: the first database row was chosen instead of the nearest team.

All tests use the isolated throwaway database from conftest.py. The LLM is always mocked (offline or a
canned reply); nothing is sent, no real alert is raised and no real team is dispatched.
"""

import asyncio
import json
import math
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Incident, RescueTeam
from app.services import incident_lifecycle as lifecycle
from app.services.ollama_service import ollama_supervisor_service as svc
from tests.conftest import sign_in

op = sign_in(TestClient(app), "operator")
cmd = sign_in(TestClient(app), "commander")
adm = sign_in(TestClient(app), "admin")
BELLANDUR = (12.9260, 77.6760)


# ------------------------------------------------------------------ helpers
@pytest.fixture
def fleet():
    """Every seeded team is set to STANDBY for the test (so only teams made here can be chosen).
    Statuses are restored afterwards and teams created by the test are parked on STANDBY."""
    db = SessionLocal()
    saved = {t.id: t.status for t in db.query(RescueTeam).all()}
    for t in db.query(RescueTeam).all():
        t.status = "STANDBY"
    db.commit()
    db.close()

    def make(lat=BELLANDUR[0] + 0.01, lon=BELLANDUR[1] + 0.01, tag="team"):
        r = op.post("/api/teams/", json=dict(
            name=f"P0 {tag}", callsign=f"P0{uuid.uuid4().hex[:6]}", vehicle_type="boat", members_count=4,
            skills="water rescue", latitude=lat, longitude=lon, base_station="Test base", contact_number="100"))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    yield make

    db = SessionLocal()
    for t in db.query(RescueTeam).all():
        t.status = saved.get(t.id, "STANDBY")
    db.commit()
    db.close()


def new_incident(people=1, severity="LOW", verify=True, lat=BELLANDUR[0], lon=BELLANDUR[1]):
    r = op.post("/api/incidents/", json=dict(
        title="P0 regression", description="Water entering homes", area="Bellandur",
        latitude=lat, longitude=lon, severity=severity, people_affected=people))
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    if verify:
        assert op.post(f"/api/incidents/{iid}/state", json={"to_status": "VERIFIED"}).status_code == 200
    return iid


def get_incident(iid):
    return op.get(f"/api/incidents/{iid}").json()


def team_status(team_id):
    return [t for t in op.get("/api/teams/").json()["items"] if t["id"] == team_id][0]["status"]


def audit_for(iid, action=None):
    items = adm.get("/api/auth/audit", params={"limit": 500}).json()["items"]
    return [e for e in items if e["target_id"] == iid and (action is None or e["action"] == action)]


def triage(iid, task_type="TRIAGE"):
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("LLM offline in test")):
        r = op.post("/api/agents/supervisor/triage", json={"task_type": task_type, "incident_id": iid})
    assert r.status_code == 201, r.text
    return r.json()


def assign(team_id, iid, client=op):
    return client.post(f"/api/teams/{team_id}/assign", json={"incident_id": iid})


def direct_db_edit(iid, **fields):
    """Simulates a bypass that skips the API entirely (a bug, a script, a manual DB edit)."""
    db = SessionLocal()
    inc = db.query(Incident).filter(Incident.id == iid).first()
    for k, v in fields.items():
        setattr(inc, k, v)
    db.commit()
    db.close()


# =========================================================================================== G5
class TestG5ApprovalBypass:
    def test_operator_cannot_downgrade_a_gated_incident_and_then_dispatch(self, fleet):
        team = fleet()
        iid = new_incident(people=9, severity="CRITICAL")
        r = op.patch(f"/api/incidents/{iid}", json={"severity": "LOW", "people_affected": 1})
        assert r.status_code == 403, f"operator downgrade was accepted ({r.status_code}): {r.text[:120]}"
        now = get_incident(iid)
        assert (now["severity"], now["people_affected"]) == ("CRITICAL", 9)
        assert assign(team, iid).status_code == 409
        assert op.post(f"/api/incidents/{iid}/state", json={"to_status": "DISPATCHED"}).status_code == 409
        assert get_incident(iid)["status"] != "DISPATCHED"

    def test_people_only_downgrade_is_blocked_too(self, fleet):
        iid = new_incident(people=9, severity="LOW")  # gated by headcount alone
        r = op.patch(f"/api/incidents/{iid}", json={"people_affected": 2})
        assert r.status_code == 403, r.text[:120]

    def test_gate_still_holds_after_a_downgrade_made_outside_the_api(self, fleet):
        team = fleet()
        iid = new_incident(people=9, severity="CRITICAL")
        direct_db_edit(iid, severity="LOW", people_affected=1)
        r = assign(team, iid)
        assert r.status_code == 409, "the gate trusted the edited fields instead of the original assessment"
        assert get_incident(iid)["status"] != "DISPATCHED"

    def test_triage_also_uses_the_original_assessment(self, fleet):
        fleet()
        iid = new_incident(people=9, severity="CRITICAL")
        direct_db_edit(iid, severity="LOW", people_affected=1)
        task = triage(iid)
        assert task["status"] == "PENDING_APPROVAL" and task["requires_human_approval"] is True
        assert get_incident(iid)["status"] == "PENDING_APPROVAL"

    def test_denied_downgrade_is_written_to_the_audit_log(self, fleet):
        iid = new_incident(people=9, severity="CRITICAL")
        op.patch(f"/api/incidents/{iid}", json={"severity": "LOW"})
        denied = audit_for(iid, "INCIDENT_RISK_DOWNGRADE_DENIED")
        assert denied and denied[0]["actor"] == "operator", "denied attempt left no audit entry"

    def test_commander_downgrade_needs_a_reason_and_is_fully_audited(self, fleet):
        team = fleet()
        iid = new_incident(people=9, severity="CRITICAL")
        assert cmd.patch(f"/api/incidents/{iid}", json={"severity": "LOW", "people_affected": 1}).status_code == 422
        r = cmd.patch(f"/api/incidents/{iid}", json={"severity": "LOW", "people_affected": 1, "note": "Verified on site: false alarm, one person on a dry roof"})
        assert r.status_code == 200, r.text[:160]
        body = r.json()
        assert (body["reported_severity"], body["reported_people_affected"]) == ("CRITICAL", 9)  # original kept
        assert body["risk_downgraded_by"] == "commander"
        assert audit_for(iid, "INCIDENT_RISK_DOWNGRADE_AUTHORIZED")
        assert assign(team, iid).status_code == 200  # a commander-authorised downgrade lifts the gate

    def test_operator_can_still_raise_risk_and_the_gate_follows(self, fleet):
        team = fleet()
        iid = new_incident(people=1, severity="LOW")
        assert op.patch(f"/api/incidents/{iid}", json={"severity": "HIGH"}).status_code == 200
        assert audit_for(iid, "INCIDENT_RISK_EDITED"), "risk edit was not audited"
        assert assign(team, iid).status_code == 409  # now gated

    def test_operator_can_still_lower_a_non_safety_incident(self, fleet):
        iid = new_incident(people=2, severity="MODERATE")
        r = op.patch(f"/api/incidents/{iid}", json={"severity": "LOW", "people_affected": 1})
        assert r.status_code == 200, r.text[:120]

    def test_unknown_severity_is_rejected(self, fleet):
        iid = new_incident(people=1, severity="LOW")
        assert op.patch(f"/api/incidents/{iid}", json={"severity": "BANANA"}).status_code == 422


# =========================================================================================== D4
class TestD4DispatchNeedsATeam:
    def test_commander_approval_with_no_available_team_does_not_dispatch(self, fleet):
        # fleet() made no team available at all
        iid = new_incident(people=9, severity="CRITICAL")
        task = triage(iid)
        assert task["suggested_team_id"] is None
        r = cmd.post(f"/api/agents/tasks/{task['id']}/approve", json={"note": "approve"})
        assert r.status_code == 409, f"approval dispatched an incident with nobody to send ({r.status_code})"
        inc = get_incident(iid)
        assert inc["status"] == "PENDING_APPROVAL" and inc["assigned_team_id"] is None
        pending = [t for t in op.get("/api/agents/tasks").json()["items"] if t["id"] == task["id"]][0]
        assert pending["status"] == "PENDING_APPROVAL"
        assert audit_for(iid, "TASK_APPROVAL_BLOCKED")

    def test_state_and_patch_endpoints_cannot_dispatch_without_a_team(self, fleet):
        iid = new_incident(people=1, severity="LOW")
        assert op.post(f"/api/incidents/{iid}/state", json={"to_status": "DISPATCHED"}).status_code == 409
        assert op.patch(f"/api/incidents/{iid}", json={"status": "DISPATCHED"}).status_code == 409
        inc = get_incident(iid)
        assert inc["status"] == "VERIFIED" and inc["assigned_team_id"] is None

    def test_patch_cannot_attach_a_team_without_dispatching(self, fleet):
        team = fleet()
        iid = new_incident(people=1, severity="LOW")
        r = op.patch(f"/api/incidents/{iid}", json={"assigned_team_id": team})
        assert r.status_code in (409, 422), r.text[:120]
        assert get_incident(iid)["assigned_team_id"] is None and team_status(team) == "AVAILABLE"

    def test_lifecycle_layer_itself_refuses_dispatched_without_a_deployed_team(self, fleet):
        iid = new_incident(people=1, severity="LOW")
        db = SessionLocal()
        try:
            inc = db.query(Incident).filter(Incident.id == iid).first()
            with pytest.raises(HTTPException) as e:
                lifecycle.transition(db, inc, "DISPATCHED", actor="test")
            assert e.value.status_code == 409
        finally:
            db.rollback()
            db.close()

    def test_assignment_claims_the_team_and_dispatches_in_one_step(self, fleet):
        team = fleet()
        iid = new_incident(people=1, severity="LOW")
        r = assign(team, iid)
        assert r.status_code == 200, r.text[:120]
        inc = get_incident(iid)
        assert inc["status"] == "DISPATCHED" and inc["assigned_team_id"] == team
        assert team_status(team) == "DEPLOYED"

    def test_a_deployed_team_cannot_be_booked_for_a_second_incident(self, fleet):
        team = fleet()
        first, second = new_incident(), new_incident()
        assert assign(team, first).status_code == 200
        r = assign(team, second)
        assert r.status_code == 409
        inc = get_incident(second)
        assert inc["status"] == "VERIFIED" and inc["assigned_team_id"] is None

    def test_an_incident_that_already_has_a_team_does_not_silently_swap_it(self, fleet):
        t1, t2 = fleet(tag="one"), fleet(tag="two")
        iid = new_incident()
        assert assign(t1, iid).status_code == 200
        assert assign(t2, iid).status_code == 409
        assert get_incident(iid)["assigned_team_id"] == t1 and team_status(t2) == "AVAILABLE"

    def test_concurrent_requests_cannot_double_book_one_team(self, fleet):
        for _ in range(6):
            team = fleet()
            a, b = new_incident(), new_incident()
            barrier = threading.Barrier(2)
            clients = [sign_in(TestClient(app), "operator"), sign_in(TestClient(app), "operator")]

            def go(args):
                c, iid = args
                barrier.wait()
                return c.post(f"/api/teams/{team}/assign", json={"incident_id": iid}).status_code

            with ThreadPoolExecutor(2) as pool:
                codes = sorted(pool.map(go, zip(clients, (a, b))))
            assert codes == [200, 409], f"double booking possible: {codes}"
            owners = [i for i in (a, b) if get_incident(i)["assigned_team_id"] == team]
            assert len(owners) == 1

    def test_failure_after_claiming_the_team_rolls_everything_back(self, fleet):
        team = fleet()
        iid = new_incident()
        boom = HTTPException(status_code=409, detail="simulated failure during the state change")
        with patch("app.services.incident_lifecycle.transition", side_effect=boom):
            r = assign(team, iid)
        assert r.status_code == 409
        assert team_status(team) == "AVAILABLE", "team stayed claimed after the dispatch failed"
        inc = get_incident(iid)
        assert inc["assigned_team_id"] is None and inc["status"] == "VERIFIED"

    def test_two_approvals_cannot_send_the_same_team_to_two_incidents(self, fleet):
        team = fleet()
        a, b = new_incident(9, "CRITICAL"), new_incident(9, "CRITICAL")
        ta, tb = triage(a), triage(b)
        assert ta["suggested_team_id"] == tb["suggested_team_id"] == team
        assert cmd.post(f"/api/agents/tasks/{ta['id']}/approve").status_code == 200
        r = cmd.post(f"/api/agents/tasks/{tb['id']}/approve")
        assert r.status_code == 409, "second approval was accepted although the team was already deployed"
        inc_b = get_incident(b)
        assert inc_b["status"] == "PENDING_APPROVAL" and inc_b["assigned_team_id"] is None
        assert get_incident(a)["status"] == "DISPATCHED" and get_incident(a)["assigned_team_id"] == team

    def test_a_team_cannot_be_released_while_its_mission_is_active(self, fleet):
        team = fleet()
        iid = new_incident()
        assert assign(team, iid).status_code == 200
        r = op.patch(f"/api/teams/{team}/status", json={"status": "AVAILABLE"})
        assert r.status_code == 409, "team was freed mid-mission and could be booked again"
        for to in ("ON_SCENE", "RESOLVED"):
            assert op.post(f"/api/incidents/{iid}/state", json={"to_status": to}).status_code == 200
        assert op.patch(f"/api/teams/{team}/status", json={"status": "AVAILABLE"}).status_code == 200


# =========================================================================================== D1
def make_team(tid, lat, lon, status="AVAILABLE"):
    return SimpleNamespace(id=tid, name=tid, latitude=lat, longitude=lon, vehicle_type="boat", skills="rescue", status=status)


def run_supervisor(teams, lat=12.93, lon=77.62, llm_choice=None):
    """Runs the supervisor on in-memory teams. The LLM is mocked: offline, or a canned JSON reply."""
    if llm_choice is None:
        patcher = patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("LLM offline in test"))
    else:
        reply = {"incident_analysis": "x", "evidence_and_freshness": "x", "risk_assessment": "HIGH",
                 "suggested_team_id": llm_choice, "suggested_facility_id": None,
                 "recommended_actions": ["go"], "requires_approval": True, "approval_rationale": "x"}
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"response": json.dumps(reply)}
        patcher = patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp)
    with patcher:
        return asyncio.run(svc.run_supervisor_reasoning(
            incident=None, target_lat=lat, target_lon=lon, target_title="t", target_area="Koramangala",
            people_count=2, task_type="TRIAGE", instruction=None, available_teams=teams,
            candidate_facilities=[], nearest_gauge=None, gauge_dist_km=0.0))


FAR, NEAR, MID = make_team("T-FAR", 13.30, 77.60), make_team("T-NEAR", 12.931, 77.621), make_team("T-MID", 13.00, 77.65)


class TestD1NearestTeam:
    def test_fallback_chooses_the_nearest_team_not_the_first_database_row(self):
        res = run_supervisor([FAR, NEAR, MID])  # the far team is listed first
        assert res.validated_team_id == "T-NEAR", f"chose {res.validated_team_id} (41 km away) over the 0.2 km team"

    def test_an_llm_suggestion_cannot_override_the_nearest_team(self):
        res = run_supervisor([NEAR, FAR, MID], llm_choice="T-FAR")  # LLM names a valid but distant team
        assert res.validated_team_id == "T-NEAR"
        assert any("T-FAR" in n and "T-NEAR" in n for n in res.validation_notes), res.validation_notes

    def test_an_llm_suggestion_is_accepted_when_it_is_the_nearest(self):
        res = run_supervisor([FAR, NEAR, MID], llm_choice="T-NEAR")
        assert res.validated_team_id == "T-NEAR"

    def test_an_invented_llm_team_id_is_rejected_and_the_nearest_is_used(self):
        res = run_supervisor([FAR, NEAR, MID], llm_choice="TEAM-DOES-NOT-EXIST")
        assert res.validated_team_id == "T-NEAR"
        assert any("REJECTED" in n for n in res.validation_notes)

    def test_unavailable_teams_are_never_selected(self):
        busy_but_close = make_team("T-BUSY", 12.9301, 77.6201, status="DEPLOYED")
        parked = make_team("T-PARKED", 12.9302, 77.6202, status="STANDBY")
        res = run_supervisor([busy_but_close, parked, FAR, MID])
        assert res.validated_team_id == "T-MID"

    def test_no_team_is_selected_when_none_are_available(self):
        res = run_supervisor([make_team("T-BUSY", 12.93, 77.62, status="DEPLOYED")])
        assert res.validated_team_id is None

    @pytest.mark.parametrize("lat,lon", [(None, 77.62), (12.93, None), (float("nan"), 77.62), (999.0, 77.62), (12.93, 400.0), (0.0, 0.0)])
    def test_teams_with_invalid_coordinates_are_skipped(self, lat, lon):
        broken = make_team("T-BROKEN", lat, lon)
        res = run_supervisor([broken, FAR, MID])
        assert res.validated_team_id == "T-MID", f"selected {res.validated_team_id}"

    def test_invalid_incident_coordinates_select_no_team(self):
        res = run_supervisor([NEAR, FAR], lat=float("nan"), lon=77.62)
        assert res.validated_team_id is None
        assert any("coordinates" in n.lower() for n in res.validation_notes), res.validation_notes

    def test_ranking_uses_exact_distance_not_a_rounded_value(self):
        a = make_team("T-A", 12.93 + 0.00004, 77.62)  # about 4.4 m away
        b = make_team("T-B", 12.93 + 0.00001, 77.62)  # about 1.1 m away; both round to 0.00 km
        assert run_supervisor([a, b]).validated_team_id == "T-B"

    def test_end_to_end_triage_and_approval_assign_the_nearest_team(self, fleet):
        far = fleet(lat=BELLANDUR[0] + 0.30, lon=BELLANDUR[1] + 0.30, tag="far")  # created first, so first row
        near = fleet(lat=BELLANDUR[0] + 0.005, lon=BELLANDUR[1] + 0.005, tag="near")
        iid = new_incident(people=9, severity="CRITICAL")
        task = triage(iid)
        assert task["suggested_team_id"] == near
        assert cmd.post(f"/api/agents/tasks/{task['id']}/approve").status_code == 200
        inc = get_incident(iid)
        assert inc["status"] == "DISPATCHED" and inc["assigned_team_id"] == near
        assert team_status(near) == "DEPLOYED" and team_status(far) == "AVAILABLE"


# ============================================================================ more paths to the same goals
class TestNoRemainingPathToUnauthorizedDispatch:
    @pytest.mark.parametrize("alias", ["DISPATCHED", "dispatched", "ASSIGNED", "assigned"])
    @pytest.mark.parametrize("gated", [False, True])
    def test_no_spelling_of_dispatched_can_be_set_by_editing_status(self, fleet, alias, gated):
        team = fleet()
        iid = new_incident(people=9, severity="CRITICAL") if gated else new_incident()
        assert op.post(f"/api/incidents/{iid}/state", json={"to_status": alias}).status_code == 409
        assert op.patch(f"/api/incidents/{iid}", json={"status": alias}).status_code == 409
        assert get_incident(iid)["status"] != "DISPATCHED" and team_status(team) == "AVAILABLE"

    def test_rescue_officer_cannot_dispatch_or_reach_another_teams_incident(self, fleet):
        officer = sign_in(TestClient(app), "officer")
        iid = new_incident()
        assert officer.post(f"/api/incidents/{iid}/state", json={"to_status": "DISPATCHED"}).status_code == 403
        assert officer.post(f"/api/teams/{fleet()}/assign", json={"incident_id": iid}).status_code == 403

    def test_dispatch_from_an_impossible_state_is_refused_before_a_team_is_touched(self, fleet):
        team = fleet()
        iid = new_incident(verify=False)  # still REPORTED
        assert assign(team, iid).status_code == 409
        assert team_status(team) == "AVAILABLE"

    def test_a_stale_team_link_from_the_old_editable_field_does_not_block_dispatch(self, fleet):
        team, stale = fleet(tag="real"), fleet(tag="stale")
        iid = new_incident()
        direct_db_edit(iid, assigned_team_id=stale)  # what the old PATCH could leave behind
        assert assign(team, iid).status_code == 200
        assert get_incident(iid)["assigned_team_id"] == team and team_status(stale) == "AVAILABLE"

    def test_approval_and_manual_assignment_cannot_both_take_the_same_team(self, fleet):
        for _ in range(4):
            team = fleet()
            gated = new_incident(9, "CRITICAL")
            ordinary = new_incident()
            task = triage(gated)
            assert task["suggested_team_id"] == team
            barrier = threading.Barrier(2)
            commander, operator = sign_in(TestClient(app), "commander"), sign_in(TestClient(app), "operator")

            def approve(_):
                barrier.wait()
                return commander.post(f"/api/agents/tasks/{task['id']}/approve").status_code

            def manual(_):
                barrier.wait()
                return operator.post(f"/api/teams/{team}/assign", json={"incident_id": ordinary}).status_code

            with ThreadPoolExecutor(2) as pool:
                f1, f2 = pool.submit(approve, 0), pool.submit(manual, 0)
                codes = sorted([f1.result(), f2.result()])
            assert codes == [200, 409], f"both paths took the team: {codes}"
            holders = [i for i in (gated, ordinary) if get_incident(i)["assigned_team_id"] == team]
            assert len(holders) == 1 and team_status(team) == "DEPLOYED"
            if get_incident(gated)["status"] != "DISPATCHED":
                assert get_incident(gated)["status"] == "PENDING_APPROVAL"  # the loser stays waiting, not half-dispatched


def test_a_risk_raise_committed_between_the_check_and_the_claim_cannot_slip_past(fleet):
    """The approval rule is evaluated again after the team is claimed. Simulate someone raising the risk in
    that window: the first check says 'no approval needed', the second says 'approval needed'."""
    team = fleet()
    iid = new_incident()
    answers = iter([False, True, True, True])
    with patch("app.services.incident_lifecycle.incident_requires_approval", side_effect=lambda inc: next(answers)):
        r = assign(team, iid)
    assert r.status_code == 409, r.text[:160]
    assert team_status(team) == "AVAILABLE", "the claim was not undone"
    inc = get_incident(iid)
    assert inc["status"] == "VERIFIED" and inc["assigned_team_id"] is None
