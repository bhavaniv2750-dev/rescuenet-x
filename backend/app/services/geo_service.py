import csv
from pathlib import Path
import struct
from typing import Any, Dict, List
from app.core.config import settings

class GeoCatchmentService:
    def __init__(self):
        self._geojson_cache: Dict[str, Any] = {}
        self._stations_cache: List[Dict[str, Any]] = []

    def get_karnataka_gauges(self) -> List[Dict[str, Any]]:
        if self._stations_cache:
            return self._stations_cache

        csv_path = settings.CLEAN_DATASET_DIR / "metadata_indofloods.csv"
        if not csv_path.exists():
            return []

        stations = []
        with open(csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                state = row.get("State", "").strip()
                if state.lower() == "karnataka":
                    try:
                        lat = float(row.get("Latitude", 0))
                        lon = float(row.get("Longitude", 0))
                        warn = float(row.get("Warning Level", 0))
                        danger = float(row.get("Danger Level", 0))
                    except ValueError:
                        continue

                    stations.append({
                        "gauge_id": row.get("GaugeID"),
                        "station_name": row.get("Station"),
                        "river": row.get("River Name/ Tributory/ SubTributory"),
                        "basin": row.get("Basin"),
                        "latitude": lat,
                        "longitude": lon,
                        "warning_level_m": warn,
                        "danger_level_m": danger,
                        "status": "MONITORING",
                    })

        self._stations_cache = stations
        return stations

    def parse_shp_polygon(self, shp_path: Path, step: int = 4) -> List[List[float]]:
        if not shp_path.exists():
            return []
        
        with open(shp_path, "rb") as f:
            data = f.read()

        pos = 100
        while pos < len(data):
            if pos + 8 > len(data):
                break
            rec_num, content_len = struct.unpack(">ii", data[pos:pos+8])
            rec_data = data[pos+8:pos+8+content_len*2]
            pos += 8 + content_len*2
            if len(rec_data) < 4:
                continue
            shape_type, = struct.unpack("<i", rec_data[0:4])
            if shape_type == 5:  # Polygon
                num_parts, num_points = struct.unpack("<2i", rec_data[36:44])
                pt_offset = 44 + num_parts * 4
                pts = []
                for i in range(0, num_points, step):
                    x, y = struct.unpack("<2d", rec_data[pt_offset+i*16:pt_offset+(i+1)*16])
                    pts.append([round(x, 5), round(y, 5)])
                # Close polygon if not closed
                if pts and pts[0] != pts[-1]:
                    pts.append(pts[0])
                return pts
        return []

    def get_catchments_geojson(self) -> Dict[str, Any]:
        if self._geojson_cache:
            return self._geojson_cache

        # Key Karnataka gauges near Bengaluru & Cauvery/Krishna basins
        target_gauges = [
            ("INDOFLOODS-gauge-361", "Shimsha / Cauvery Sub-catchment (Bengaluru West/South)", "#06b6d4"),
            ("INDOFLOODS-gauge-394", "Biligundulu / Cauvery Mainstem Catchment", "#3b82f6"),
            ("INDOFLOODS-gauge-372", "Gurupur Coastal Basin", "#10b981"),
            ("INDOFLOODS-gauge-396", "Swarna River Catchment", "#8b5cf6"),
            ("INDOFLOODS-gauge-397", "Ghataprabha River Basin", "#ec4899"),
        ]

        features = []
        for gauge_id, catchment_name, color in target_gauges:
            shp_path = settings.SHAPEFILES_DIR / f"{gauge_id}.shp"
            coords = self.parse_shp_polygon(shp_path, step=4)
            if coords:
                features.append({
                    "type": "Feature",
                    "properties": {
                        "gauge_id": gauge_id,
                        "catchment_name": catchment_name,
                        "color": color,
                        "points_count": len(coords),
                        "source": "IndoFloods Catchments Shapefiles",
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords],
                    },
                })

        geojson = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "total_catchments": len(features),
                "region": "Karnataka / Bengaluru Hydrological Catchments",
                "crs": "EPSG:4326 (WGS84)",
            },
        }
        self._geojson_cache = geojson
        return geojson

geo_service = GeoCatchmentService()
