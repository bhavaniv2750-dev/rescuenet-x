"""Choosing a rescue team by distance.

Every path that picks a team (the supervisor's rule-based fallback and its reply from the language model)
goes through select_team(), so the choice cannot depend on database order or on what the model says.

Rules:
  * only teams whose status is AVAILABLE are eligible;
  * a team needs valid coordinates (finite numbers inside -90..90 / -180..180, and not the (0, 0) placeholder);
  * the incident needs valid coordinates too, otherwise no team is chosen;
  * teams are ranked by exact great-circle (Haversine) distance, ties broken by team id so results repeat;
  * a team suggested by the model is accepted only when it is the nearest eligible team (within 50 m).
"""

import math
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

EARTH_RADIUS_KM = 6371.0088
TIE_TOLERANCE_KM = 0.05


def haversine_km_exact(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres, not rounded (rounding would create false ties)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def valid_coordinates(lat: Any, lon: Any) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    return not (lat == 0.0 and lon == 0.0)  # (0, 0) is a "no position" placeholder, not a place in Karnataka


@dataclass
class RankedTeam:
    team: Any
    distance_km: float


@dataclass
class TeamSelection:
    team: Optional[Any]
    distance_km: Optional[float]
    ranked: List[RankedTeam] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def rank_available_teams(teams: Sequence[Any], lat: Any, lon: Any) -> Tuple[List[RankedTeam], List[str]]:
    """Eligible teams nearest first, plus a note for every team that was skipped and why."""
    if not valid_coordinates(lat, lon):
        return [], ["Incident coordinates are missing or invalid, so no team can be ranked by distance."]
    ranked: List[RankedTeam] = []
    skipped: List[str] = []
    for t in teams:
        status = str(getattr(t, "status", "") or "").upper()
        if status != "AVAILABLE":
            skipped.append(f"Skipped team '{t.id}': status is {status or 'unknown'}, not AVAILABLE.")
            continue
        if not valid_coordinates(getattr(t, "latitude", None), getattr(t, "longitude", None)):
            skipped.append(f"Skipped team '{t.id}': invalid or missing coordinates.")
            continue
        ranked.append(RankedTeam(t, haversine_km_exact(float(lat), float(lon), float(t.latitude), float(t.longitude))))
    ranked.sort(key=lambda r: (r.distance_km, str(r.team.id)))
    return ranked, skipped


def select_team(teams: Sequence[Any], lat: Any, lon: Any, preferred_id: Optional[str] = None) -> TeamSelection:
    """The nearest eligible team. preferred_id (for example a model's suggestion) can only confirm that choice."""
    ranked, skipped = rank_available_teams(teams, lat, lon)
    notes: List[str] = []
    if not ranked:
        if valid_coordinates(lat, lon):
            notes.append("No response teams currently AVAILABLE in database.")
        if preferred_id:
            notes.insert(0, f"REJECTED hallucinated/invalid team ID '{preferred_id}'.")
        return TeamSelection(None, None, [], notes + skipped)

    nearest = ranked[0]
    if preferred_id:
        match = next((r for r in ranked if str(r.team.id) == str(preferred_id)), None)
        if match is None:
            notes.append(f"REJECTED hallucinated/invalid team ID '{preferred_id}' (not an eligible AVAILABLE team).")
        elif match.distance_km <= nearest.distance_km + TIE_TOLERANCE_KM:
            notes.append(f"Team ID '{match.team.id}' verified as AVAILABLE in database and is the nearest eligible team ({match.distance_km:.2f} km).")
            return TeamSelection(match.team, match.distance_km, ranked, notes + skipped)
        else:
            notes.append(
                f"Overrode suggested team '{match.team.id}' ({match.distance_km:.2f} km): "
                f"the nearest available team is '{nearest.team.id}' ({nearest.distance_km:.2f} km)."
            )
    notes.append(
        f"Deterministically assigned closest available team '{nearest.team.name}' ({nearest.team.id}) at {nearest.distance_km:.2f} km."
    )
    return TeamSelection(nearest.team, nearest.distance_km, ranked, notes + skipped)
