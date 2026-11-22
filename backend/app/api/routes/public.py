"""Public emergency reporting and report tracking. No account is required for any route here."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user
from app.api.routes.incidents import create_report
from app.core.config import settings
from app.db.session import get_db
from app.models.entities import Incident, MediaAsset, User
from app.schemas.domain import IncidentCreate
from app.services import public_refs, rate_limit
from app.services.rate_limit import client_ip

router = APIRouter()

PUBLIC_STATUS = {
    "REPORTED": "Received", "UNDER_VERIFICATION": "Received",
    "VERIFIED": "Being assessed", "QUEUED": "Being assessed", "TRIAGE_IN_PROGRESS": "Being assessed",
    "PENDING_APPROVAL": "Being assessed",
    "DISPATCHED": "A rescue team has been assigned", "IN_TRANSIT": "A rescue team has been assigned",
    "ON_SCENE": "Responders are at the location",
    "RESOLVED": "Resolved", "DUPLICATE": "Merged with another report", "REJECTED": "Closed", "CANCELLED": "Closed",
}
NOT_FOUND = "No report matches that reference and tracking code."
DANGER_NOTE = "This is a report-tracking page, not an emergency line. If you are in immediate danger, call 112."


@router.post("/reports", status_code=status.HTTP_201_CREATED)
def submit_report(payload: IncidentCreate, request: Request, db: Session = Depends(get_db),
                  user: Optional[User] = Depends(get_optional_user)):
    """Report an emergency. Returns only what the reporter needs: a reference, a secret tracking code (shown once)
    and a plain status. Internal incident ids are not returned."""
    incident, code, photos, warnings = create_report(db, payload, request, user)
    return {
        "public_ref": incident.public_ref,
        "tracking_code": code,
        "status": PUBLIC_STATUS.get(incident.status, "Received"),
        "received_at": incident.created_at,
        "photos_attached": photos,
        "photo_warnings": warnings,
        "notice": "Save the tracking code now; it is shown only once and cannot be recovered. " + DANGER_NOTE,
    }


@router.get("/reports/{public_ref}")
def track_report(public_ref: str, request: Request, db: Session = Depends(get_db),
                 x_tracking_code: Optional[str] = Header(default=None)):
    """Limited status for a reporter. The tracking code travels in a header so it does not end up in URLs or logs.
    An unknown reference and a wrong code give exactly the same answer."""
    ip = rate_limit.client_fingerprint(request)
    rate_limit.check("track-lookups", ip, settings.TRACKING_LOOKUPS_PER_HOUR, 3600)
    if rate_limit.too_many("track-failures", ip, settings.TRACKING_FAILURES_PER_15_MIN, 900):
        raise HTTPException(status_code=429, headers={"Retry-After": "900"},
                            detail=f"Too many unsuccessful attempts. Please wait 15 minutes. {rate_limit.EMERGENCY_NOTE}")

    ref = public_refs.normalise_ref(public_ref)
    inc = db.query(Incident).filter(Incident.public_ref == ref).first() if ref else None
    ok = public_refs.code_matches(x_tracking_code or "", inc.tracking_code_hash if inc else None)
    if not (inc and ok):
        rate_limit.record("track-failures", ip)
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    photos = db.query(MediaAsset).filter(MediaAsset.incident_id == inc.id).count()
    return {
        "public_ref": inc.public_ref,
        "status": PUBLIC_STATUS.get(inc.status, "Received"),
        "received_at": inc.created_at,
        "updated_at": inc.updated_at,
        "photo_count": photos,
        "notice": DANGER_NOTE,
    }
