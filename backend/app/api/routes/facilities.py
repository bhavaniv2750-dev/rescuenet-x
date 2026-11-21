import math
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.api.deps import actor_name, actor_role, require_roles
from app.core.security import APPROVERS, DEPT, OPS
from app.db.session import get_db
from app.models.entities import Facility, User
from app.services.audit import record_audit
from app.services.facilities import capacity_status
from app.schemas.domain import FacilityCreate, FacilityOccupancyUpdate, FacilityOut

router = APIRouter()

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

@router.get("/", response_model=dict)
def list_facilities(
    facility_type: Optional[str] = Query(None, alias="type"),
    user_lat: Optional[float] = Query(None, alias="lat"),
    user_lon: Optional[float] = Query(None, alias="lon"),
    db: Session = Depends(get_db),
):
    query = db.query(Facility)
    if isinstance(facility_type, str) and facility_type.strip():
        query = query.filter(Facility.facility_type == facility_type.upper())

    facilities = query.all()
    results = []

    has_coords = isinstance(user_lat, (int, float)) and isinstance(user_lon, (int, float))
    for fac in facilities:
        data = FacilityOut.model_validate(fac)
        if has_coords:
            data.distance_km = haversine_km(float(user_lat), float(user_lon), fac.latitude, fac.longitude)
        else:
            # Default reference distance from Central Bengaluru (12.9716, 77.5946)
            data.distance_km = haversine_km(12.9716, 77.5946, fac.latitude, fac.longitude)
        results.append(data)

    results.sort(key=lambda x: x.distance_km if x.distance_km is not None else 9999)

    return {
        "items": results,
        "count": len(results),
        "total_capacity": sum(f.total_capacity for f in facilities),
        "total_occupancy": sum(f.current_occupancy for f in facilities),
    }

@router.post("/", response_model=FacilityOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(*OPS))])
def create_facility(payload: FacilityCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    prefix = payload.facility_type.upper().split("_")[0][:5]
    number = db.query(Facility).count() + 1
    new_id = f"FAC-{prefix}-{number:02d}"
    while db.query(Facility).filter(Facility.id == new_id).first():
        number += 1
        new_id = f"FAC-{prefix}-{number:02d}"

    facility = Facility(
        id=new_id,
        name=payload.name,
        facility_type=payload.facility_type.upper(),
        address=payload.address,
        latitude=payload.latitude,
        longitude=payload.longitude,
        total_capacity=payload.total_capacity,
        current_occupancy=payload.current_occupancy,
        status=capacity_status(payload.current_occupancy, payload.total_capacity),
        contact=payload.contact,
        data_label="OBSERVED",
    )
    db.add(facility)
    record_audit(db, actor_name(user), "FACILITY_CREATED", "facility", new_id, f"{payload.facility_type.upper()} {payload.name}", role=actor_role(user))
    db.commit()
    db.refresh(facility)
    return FacilityOut.model_validate(facility)


@router.patch("/{facility_id}/occupancy", response_model=FacilityOut)
def update_occupancy(facility_id: str, payload: FacilityOccupancyUpdate, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*OPS))):
    """Update how many people a facility holds; the status follows from the numbers."""
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail=f"Facility {facility_id} not found")
    capacity = payload.total_capacity or facility.total_capacity
    if payload.current_occupancy > capacity:
        raise HTTPException(status_code=422, detail="current_occupancy cannot be more than total_capacity")
    facility.total_capacity = capacity
    facility.current_occupancy = payload.current_occupancy
    facility.status = capacity_status(payload.current_occupancy, capacity)
    record_audit(db, actor_name(user), "FACILITY_OCCUPANCY", "facility", facility.id,
                 f"{payload.current_occupancy}/{capacity} ({facility.status})", role=actor_role(user))
    db.commit()
    db.refresh(facility)
    return FacilityOut.model_validate(facility)
