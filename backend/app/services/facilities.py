"""Facility types and the capacity status rule."""

FACILITY_TYPES = [
    "HOSPITAL",       # emergency beds
    "SHELTER",        # evacuation shelter
    "RELIEF_CAMP",    # food, water and supplies
    "RESCUE_HQ",      # rescue force base
    "POLICE_STATION",
    "FIRE_STATION",
    "SCHOOL",         # school opened as a shelter
]

NEAR_CAPACITY_RATIO = 0.9


def capacity_status(occupancy: int, capacity: int) -> str:
    """FULL at 100%, NEAR_CAPACITY from 90%, otherwise OPERATIONAL."""
    if capacity <= 0 or occupancy >= capacity:
        return "FULL"
    if occupancy >= NEAR_CAPACITY_RATIO * capacity:
        return "NEAR_CAPACITY"
    return "OPERATIONAL"
