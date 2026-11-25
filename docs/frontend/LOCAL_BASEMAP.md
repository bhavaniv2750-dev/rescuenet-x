# Local (offline) basemap

## Why the basemap was blank: diagnosis
In the cloud build environment every request to a tile host fails at the egress proxy, before it reaches the provider:

| Check | Result |
|---|---|
| `*.basemaps.cartocdn.com`, `tile.openstreetmap.org` | proxy answers **403 on CONNECT** (browser: `ERR_TUNNEL_CONNECTION_FAILED`) |
| `nominatim`, `overpass`, `download.geofabrik.de`, `download.bbbike.org` | same 403 (host not on the sandbox allowlist) |
| Reachable | `raw.githubusercontent.com` (exact paths), `naturalearth.s3.amazonaws.com`, PyPI, npm, git clone of public GitHub repos |

So the cause is the **sandbox network allowlist**, not an API key (none is used), not CSP, not the Leaflet tile configuration, and not a provider block. The same tile URLs work on a normal network. The sandbox restriction was not bypassed and no proxy was added.

## Architecture
`InteractiveMap` chooses the base map through a chain: **configured online map -> permitted secondary online map (CARTO <-> OSM standard) -> local map -> "No base map available" notice**. The step advances after 3 tile errors with no successful tile, or after 6 s with nothing loaded. Users can also pick "Automatic", a specific online map, or "Local offline map" under *Style and layers*. A chip shows the active source ("Online map: X", "Online map: X (fallback)", "Offline map: locally stored data").

The local map (`src/components/Map/localBasemap.ts`) draws bundled GeoJSON on two Leaflet canvas panes (geometry below overlays, labels above). Dark and light palettes are applied, with small tweaks per preset. Detail is zoom dependent (ward polygons from zoom 9, ward names from 12, collision-aware labels capped at 90). All markers, rings, clusters, catchments, legends, search, fullscreen and recenter are unchanged and work on top of it. Files are fetched lazily, only when the local map is needed, and memoized.

## Data (acquired 2026-11-25)
| Layer | Source | Licence |
|---|---|---|
| Highways, railways, rivers, lakes, urban areas, state boundaries, towns, airports | Natural Earth 10m (naturalearthdata.com) | Public domain |
| 243 BBMP ward polygons (2022) with names | DataMeet Municipal_Spatial_Data (BBMP.geojson) | CC BY-SA 2.5 India |

Both are clipped to the Karnataka window and simplified (0.004 deg for Natural Earth, 0.0002 deg for wards, 4 decimals). Attribution is shown on the map and recorded in `public/basemap/manifest.json`. Rebuild with `scripts/build_local_basemap.py` (needs `pyshp`, `shapely`).

## Actual coverage and limits (be explicit in the report)
Present: ward boundaries and names (neighbourhood-level), major highways, rail, rivers, lakes, urban extent, towns, airport labels. All 9 seeded facilities fall inside the expected BBMP ward polygons.
**Not present: residential/secondary streets, building footprints, parks, landmarks.** No OpenStreetMap extract could be downloaded from the build environment. Nothing was fabricated. Ward polygons are administrative boundaries, not land-use. Catchments remain historical boundaries, not flooded areas.

## Adding street-level OpenStreetMap data (optional, one-time, on your machine)
Licence: ODbL 1.0, (c) OpenStreetMap contributors (attribution is shown by the map and written to the manifest).
1. Download the Bangalore extract: https://download.bbbike.org/osm/bbbike/Bangalore/ (file `Bangalore.osm.pbf`, tens of MB). Alternative: https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf (large; the script clips by `--bbox`).
2. Windows PowerShell, from `rescuenet-x2\frontend`:
```powershell
pip install osmium shapely
python scripts\build_osm_layers.py --pbf C:\data\Bangalore.osm.pbf --out public\basemap
# optional building footprints (large files): add --buildings
```
3. Restart the dev server or rebuild. The map loads `public/basemap/osm_roads.json`, `osm_water.json`, `osm_parks.json`, `osm_places.json`, `osm_landmarks.json` (and `osm_buildings.json`) automatically, and local search also covers those names.
`build_osm_layers.py` was exercised only on a tiny synthetic OSM XML fixture (produced the road and place layers); it has not been run on a real Bangalore extract here.

## Verification performed
Playwright with `basemaps.cartocdn.com`, `tile.openstreetmap.org` and Nominatim requests aborted: all four presets (Classic, Tactical, Navigation, Flood Intelligence) at the same view, 1440 and 390 px, show geography, markers on the correct wards, catchments aligned, chip "Offline map: locally stored data". Screenshots: `docs/evidence/GIS/offline/` (`*_1440.png`, `*_390.png`, `navigation_light_*` for light styling and local search). Local search "kora" returns Koramangala (ward 186) and flies to it. Tests: `localBasemap.test.ts` (data integrity, no false OSM claim, search, palettes).

## Performance
Bundled data 316 KB raw (wards 194 KB, about 41 KB gzipped); loaded only on fallback. App JS bundle unchanged apart from about 8 KB of code. Panning/zooming stays smooth on the canvas renderer in headless Chromium (not benchmarked on a real device).

## Search privacy
Search is local first and sends nothing. "Search online instead" is a separate explicit button that sends the typed text to OSM Nominatim; its results are labelled online.


## Regional archive (South India)
A larger optional layer built from the Geofabrik Southern Zone PBF is described in [REGIONAL_GIS.md](REGIONAL_GIS.md). It sits between the online maps and this basic local map in the fallback chain; this bundled map stays the last offline fallback and is used whenever the regional archive is absent.
