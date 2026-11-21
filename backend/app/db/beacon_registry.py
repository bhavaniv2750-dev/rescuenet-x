"""Simulated registry of 35 LoRa beacons at Bengaluru flood hotspots.

Positions are approximate locality centres and are labelled SIMULATED.
They are used only for testing the LoRa intake pipeline.

Note: the clean_rescuenet_sos_data.csv file in the repository has Mumbai
coordinates (latitude about 19.1, longitude about 72.9), so it is kept as an
external reference dataset and is not used for the Bengaluru map.
"""

BENGALURU_HOTSPOTS = [
    ("BCN-001", "Bellandur", 12.9260, 77.6762),
    ("BCN-002", "Varthur", 12.9400, 77.7470),
    ("BCN-003", "HSR Layout", 12.9116, 77.6474),
    ("BCN-004", "K R Puram", 13.0076, 77.6950),
    ("BCN-005", "Hebbal", 13.0358, 77.5970),
    ("BCN-006", "Mahadevapura", 12.9916, 77.7024),
    ("BCN-007", "Sarjapur Road", 12.9100, 77.6870),
    ("BCN-008", "Yemalur", 12.9580, 77.6950),
    ("BCN-009", "Koramangala", 12.9352, 77.6245),
    ("BCN-010", "Silk Board", 12.9176, 77.6230),
    ("BCN-011", "Hoodi", 12.9920, 77.7150),
    ("BCN-012", "Whitefield", 12.9698, 77.7500),
    ("BCN-013", "Marathahalli", 12.9592, 77.6974),
    ("BCN-014", "Domlur", 12.9610, 77.6387),
    ("BCN-015", "Ejipura", 12.9440, 77.6260),
    ("BCN-016", "Shanthinagar", 12.9560, 77.6000),
    ("BCN-017", "Hosakerehalli", 12.9300, 77.5400),
    ("BCN-018", "Nayandahalli", 12.9440, 77.5250),
    ("BCN-019", "Vrishabhavathi Valley", 12.9100, 77.4850),
    ("BCN-020", "Nagavara", 13.0440, 77.6210),
    ("BCN-021", "Manyata Tech Park", 13.0480, 77.6200),
    ("BCN-022", "Yelahanka", 13.1007, 77.5963),
    ("BCN-023", "Jakkur", 13.0780, 77.6060),
    ("BCN-024", "Hennur", 13.0330, 77.6400),
    ("BCN-025", "Rajarajeshwari Nagar", 12.9270, 77.5180),
    ("BCN-026", "Kengeri", 12.9080, 77.4820),
    ("BCN-027", "Bommanahalli", 12.9080, 77.6230),
    ("BCN-028", "Begur", 12.8760, 77.6290),
    ("BCN-029", "Electronic City", 12.8450, 77.6600),
    ("BCN-030", "Madiwala", 12.9220, 77.6170),
    ("BCN-031", "Agara", 12.9240, 77.6420),
    ("BCN-032", "Kadubeesanahalli", 12.9370, 77.6970),
    ("BCN-033", "Panathur", 12.9390, 77.7150),
    ("BCN-034", "Horamavu (Sai Layout)", 13.0260, 77.6630),
    ("BCN-035", "Indiranagar", 12.9784, 77.6408),
]

# Operating area accepted by the LoRa intake endpoint.
KARNATAKA_BOUNDS = {"lat_min": 11.5, "lat_max": 15.5, "lon_min": 74.0, "lon_max": 78.5}


def inside_karnataka(lat: float, lon: float) -> bool:
    b = KARNATAKA_BOUNDS
    return b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]
