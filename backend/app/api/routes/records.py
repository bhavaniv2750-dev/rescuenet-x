import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.models.entities import RescueRecord
from app.schemas.domain import RescueRecordCreate, RescueRecordOut

router = APIRouter()

@router.get("/export/csv")
def export_records_csv(db: Session = Depends(get_db)):
    records = db.query(RescueRecord).order_by(RescueRecord.completed_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    
    # Write professional headers
    writer.writerow([
        "Record ID",
        "Incident ID",
        "Rescue Team ID",
        "Operational Location / Area",
        "People Rescued",
        "Survivors",
        "Missing Persons",
        "Deceased Count",
        "Severe Injuries",
        "Minor Injuries",
        "Mission Debrief Notes",
        "Completed At (UTC)",
    ])
    
    for r in records:
        writer.writerow([
            r.id,
            r.incident_id,
            r.team_id,
            r.location or "",
            r.people_rescued,
            r.survivors,
            r.missing,
            r.deceased,
            r.severe_injuries,
            r.minor_injuries,
            (r.notes or "").replace("\r\n", " ").replace("\n", " "),
            r.completed_at.isoformat() if r.completed_at else "",
        ])
    
    csv_bytes = output.getvalue().encode("utf-8-sig")  # utf-8 with BOM for Excel compatibility
    filename = f"RescueNet_Missions_Archive_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )

@router.get("/", response_model=dict)
def list_records(db: Session = Depends(get_db)):
    records = db.query(RescueRecord).order_by(RescueRecord.completed_at.desc()).all()
    return {
        "items": [RescueRecordOut.model_validate(r) for r in records],
        "count": len(records),
    }

@router.get("/summary")
def get_records_summary(db: Session = Depends(get_db)):
    totals = db.query(
        func.sum(RescueRecord.people_rescued).label("rescued"),
        func.sum(RescueRecord.survivors).label("survivors"),
        func.sum(RescueRecord.missing).label("missing"),
        func.sum(RescueRecord.deceased).label("deceased"),
        func.sum(RescueRecord.severe_injuries).label("severe_injuries"),
        func.sum(RescueRecord.minor_injuries).label("minor_injuries"),
    ).first()

    return {
        "total_missions": db.query(RescueRecord).count(),
        "total_rescued": int(totals.rescued or 0),
        "total_survivors": int(totals.survivors or 0),
        "total_missing": int(totals.missing or 0),
        "total_deceased": int(totals.deceased or 0),
        "total_severe_injuries": int(totals.severe_injuries or 0),
        "total_minor_injuries": int(totals.minor_injuries or 0),
    }

@router.post("/", response_model=RescueRecordOut, status_code=status.HTTP_201_CREATED)
def create_record(payload: RescueRecordCreate, db: Session = Depends(get_db)):
    count = db.query(RescueRecord).count()
    new_id = f"REC-2026-{count + 3:03d}"

    record = RescueRecord(
        id=new_id,
        incident_id=payload.incident_id,
        team_id=payload.team_id,
        location=payload.location,
        people_rescued=payload.people_rescued,
        survivors=payload.survivors,
        missing=payload.missing,
        deceased=payload.deceased,
        severe_injuries=payload.severe_injuries,
        minor_injuries=payload.minor_injuries,
        notes=payload.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return RescueRecordOut.model_validate(record)
