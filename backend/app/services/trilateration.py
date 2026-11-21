"""Estimate a LoRa beacon position from signal strength at several gateways.

Signal strength (RSSI) is turned into an approximate distance with the
log-distance path loss model, d = 10 ** ((P_ref - RSSI) / (10 * n)), and the
position is the least-squares fit to all gateway distances. Coordinates are
projected to a local metric grid (equirectangular, accurate over a few km).
"""

import math
from typing import List, Sequence, Tuple

import numpy as np

EARTH_RADIUS_M = 6_371_000.0
DEFAULT_REF_RSSI_DBM = -40.0  # expected RSSI at 1 m from the beacon
DEFAULT_PATH_LOSS_EXP = 2.7   # urban, partly obstructed


def rssi_to_distance_m(rssi_dbm: float, ref_rssi_dbm: float = DEFAULT_REF_RSSI_DBM, n: float = DEFAULT_PATH_LOSS_EXP) -> float:
    return 10 ** ((ref_rssi_dbm - rssi_dbm) / (10 * n))


def _to_local(lat: float, lon: float, lat0: float, lon0: float) -> Tuple[float, float]:
    x = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_RADIUS_M
    return x, y


def _to_geo(x: float, y: float, lat0: float, lon0: float) -> Tuple[float, float]:
    lat = lat0 + math.degrees(y / EARTH_RADIUS_M)
    lon = lon0 + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(lat0))))
    return lat, lon


def trilaterate(gateways: Sequence[Tuple[float, float, float]]) -> Tuple[float, float, float]:
    """gateways: (latitude, longitude, distance_m) for at least three gateways.

    Returns (latitude, longitude, rms_residual_m).
    """
    if len(gateways) < 3:
        raise ValueError("At least three gateway readings are needed for trilateration")
    lat0 = sum(g[0] for g in gateways) / len(gateways)
    lon0 = sum(g[1] for g in gateways) / len(gateways)
    pts = [(*_to_local(g[0], g[1], lat0, lon0), g[2]) for g in gateways]

    # Linearise by subtracting the first circle equation from the others.
    x1, y1, d1 = pts[0]
    rows: List[List[float]] = []
    rhs: List[float] = []
    for xi, yi, di in pts[1:]:
        rows.append([2 * (xi - x1), 2 * (yi - y1)])
        rhs.append(d1 ** 2 - di ** 2 + xi ** 2 - x1 ** 2 + yi ** 2 - y1 ** 2)
    A = np.array(rows)
    b = np.array(rhs)
    if np.linalg.matrix_rank(A) < 2:
        raise ValueError("Gateways are collinear; position cannot be resolved")
    (x, y), *_ = np.linalg.lstsq(A, b, rcond=None)

    # Refine with a few Gauss-Newton steps on the true range residuals.
    for _ in range(10):
        J, r = [], []
        for xi, yi, di in pts:
            dist = max(math.hypot(x - xi, y - yi), 1e-6)
            J.append([(x - xi) / dist, (y - yi) / dist])
            r.append(dist - di)
        J = np.array(J)
        r = np.array(r)
        step, *_ = np.linalg.lstsq(J, -r, rcond=None)
        x, y = x + step[0], y + step[1]
        if math.hypot(step[0], step[1]) < 0.01:
            break

    rms = float(math.sqrt(sum((math.hypot(x - xi, y - yi) - di) ** 2 for xi, yi, di in pts) / len(pts)))
    lat, lon = _to_geo(x, y, lat0, lon0)
    return lat, lon, rms
