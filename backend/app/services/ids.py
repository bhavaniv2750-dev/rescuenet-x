"""Identifier helpers that cannot collide, even after rows are deleted."""

from sqlalchemy.orm import Session

from app.models.entities import Volunteer


def next_volunteer_id(db: Session) -> str:
    """VOL-<n>, one more than the highest number in use (starting at 101)."""
    highest = 100
    for (vid,) in db.query(Volunteer.id).all():
        try:
            highest = max(highest, int(str(vid).split("-")[1]))
        except (IndexError, ValueError):
            continue
    return f"VOL-{highest + 1}"
