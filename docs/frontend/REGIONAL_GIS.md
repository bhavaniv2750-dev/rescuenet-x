# Regional GIS architecture: South India vector tiles (PMTiles)

Status: **implemented and tested with a synthetic fixture; NOT yet generated from the real Geofabrik file.** Full South India rendering is not claimed until you generate and verify the archive on Windows (section 11).

Evidence labels used below: **[cloud]** verified in the cloud build environment, **[fixture]** verified on a synthetic test fixture, **[doc]** taken from the tool's own documentation (fetched 2026-11-25), **[estimate]** my estimate, **[to measure]** only your Windows run can measure.

## 1. Recommended architecture
```
southern-zone-261124.osm.pbf  (read once, never copied, never converted to GeoJSON)
        |  Planetiler + Protomaps basemap profile (disk-backed, streaming)         [Windows, one-off]
        v
south-india.pmtiles   one compressed, spatially indexed vector tile archive (all zooms, all themes, all presets)
        |  node scripts/serve_tiles.mjs  (127.0.0.1, HTTP Range)
        v
browser: Leaflet + protomaps-leaflet  -> requests only the tiles of the current view (Range requests), draws them on canvas
        style = light|dark flavour  x  preset tweak (Classic / Tactical / Navigation / Flood Intelligence)   [same geometry]
Also: search/  compact sharded name index (separate from the tiles; PMTiles has no geocoder)
```
No second geographical database exists for any preset or theme: a style is a set of colours applied at draw time.

Fallback order (unchanged, one step added): configured online map -> secondary online map -> **regional archive (if configured and reachable)** -> basic local map (Natural Earth + BBMP wards, bundled) -> "No base map available". The regional archive can also be chosen manually ("Regional offline map"). If it is missing or the server is down, the probe fails silently and the existing basic local map keeps working **[fixture: verified with the archive request blocked]**.

## 2. Tool evaluation
| Tool | Output | Memory / disk (own docs) | Windows / setup | Verdict |
|---|---|---|---|---|
| **Planetiler** + Protomaps basemap profile | PMTiles directly | heap about 0.5x PBF, free RAM left for memory-mapped files; temp disk 1 GB + 5 to 10x PBF **[doc]** | Needs a JDK and Maven to build the Protomaps profile (profile README: Java 21+); Planetiler's own README now says Java 25+. Both are installed portably under one folder by the script (no system install) | **Chosen**: memory-efficient by design, official Protomaps schema, direct PMTiles output |
| Planetiler launcher exe (OpenMapTiles profile) | PMTiles / MBTiles | same | No Java needed (experimental single-file launcher) | Not chosen: OpenMapTiles schema has no ready-made protomaps-leaflet styles; I would have to hand-write every style rule without real data to test against |
| tilemaker | PMTiles / MBTiles | RAM by default; `--store <ssd dir>` makes it disk-backed **[doc]** | Windows binary, no Java | Good fallback if the Java route fails; needs its own Lua/JSON config and a different schema, so styles would need rework |
| Tippecanoe / GeoJSON route | needs GeoJSON of the whole PBF | huge intermediate files | n/a | Rejected (violates the no-GeoJSON, no-intermediate-files rules) |
| MBTiles instead of PMTiles | SQLite | same generation cost | needs a tile server with SQL | Not needed: PMTiles is one static file readable with HTTP Range, no server logic |

Compatibility facts checked **[cloud]**: `protomaps-leaflet` 5.1.0 (BSD-3) renders PMTiles vector tiles in Leaflet; `pmtiles` 4.5 (BSD-3); `@protomaps/basemaps` 5.0.0 provides the light/dark flavours; all three are free, keyless and need no service.

## 3. Resource estimates (disk, memory, CPU)
PBF: 534.46 MB (given). The persistent budget target is about 3 GB including the PBF; temporary space is estimated separately.

| Item | Estimate | Basis |
|---|---|---|
| Original PBF | 0.53 GB | given, preserved, only read |
| Temporary processing (peak) | 2.7 to 5.3 GB | Planetiler doc: 5 to 10x PBF **[doc]** |
| Downloaded sources (Natural Earth, water polygons) | about 1 to 2 GB, deleted after validation | **[estimate]** |
| JDK + Maven + profile build | about 0.5 to 1 GB (deletable with `-Tools`) | **[estimate]** |
| Output archive `south-india.pmtiles` | about 0.5 to 1.5 GB | **[estimate]**: Protomaps planet builds are roughly 1.5x their source PBF; buildings dominate |
| Search index | about 5 to 30 MB gzipped | **[estimate]** (a few hundred thousand names) |
| **Persistent after cleanup** | **about 1.2 to 2.5 GB including the PBF: inside the 3 GB target** | **[estimate]** |
| **Peak during processing** | **about 8 to 11 GB free needed** (`Check` requires about 12 GB) | **[estimate]** |
| Memory | Java heap 3 GB (`-Xmx3g`), total process about 3 to 4 GB; mmap pages are reclaimable cache | heap guidance **[doc]**; process total **[to measure]** |
| CPU | 4 threads of 12, BelowNormal priority; no GPU | design choice |

The `Check` step warns if free space is below the peak estimate, and `Build` is never run without your explicit `-Approve` after you have read the benchmark numbers (the 8 to 11 GB estimate is **not** pre-approved). The `Benchmark` step builds Bengaluru only from the same file and prints elapsed time and **measured** peak memory: use it before the full build, and report its numbers back rather than trusting the estimates above.

## 4. Coverage and features
The Protomaps basemap schema is designed to contain: earth, water (lakes, reservoirs, rivers), landuse/landcover (parks, forests, hospital/school/college areas, airports), roads (highway, major, medium, minor, service/other, paths, rail), buildings (high zoom only), places (cities, towns, suburbs, neighbourhoods, villages), pois (hospitals, schools, colleges, stations, airports, landmarks) and boundaries (national, state, district). **[doc]** Which of these actually exist in your archive, and the true geographical extent, are **[to measure]**: `-Step Validate` prints the PBF bounding box and `-Step Verify` prints the archive bounds and layer list. Geofabrik's "Southern Zone" is expected to cover the southern Indian states and union territories, but the extent is whatever the PBF header says.

Zoom-dependent detail is built into the profile (regional to city to street; buildings and minor roads only at high zoom). "Coverage" here is geographical map coverage only; it does **not** mean rescue operations, flood prediction or hydrology exist for those regions. The app's operational data (incidents, squads, facilities, gauges, catchments) remains the Bengaluru demonstration data.

## 5. Viewport rendering and caching
The browser reads the 127-byte header (and the small metadata), then fetches only the directory pages and tiles for the current view with HTTP Range requests. State-level data is never loaded whole. Memory is bounded by protomaps-leaflet's tile cache, and the browser HTTP cache is size-limited by the browser; the local server sends `Cache-Control: public, max-age=3600`. **[fixture]**: a pan/zoom session at Bengaluru issued 16 to 30 small Range requests, not a full download.

## 6. Frontend compatibility: Leaflet kept, MapLibre assessed, not adopted
Implemented with the existing Leaflet map via `protomaps-leaflet`, lazily imported (about 125 KB raw / 35 KB gzip chunk, loaded only when the archive is used; the main bundle grew by about 12 KB for the theme system). All operational layers are untouched.

MapLibre GL JS comparison (assessment only, **no migration performed**):
| | Leaflet + protomaps-leaflet (now) | MapLibre GL JS + PMTiles protocol |
|---|---|---|
| Rendering | Canvas 2D per tile, labels collision-checked per tile | WebGL, GPU, smooth zoom/rotation, best label quality |
| Styles | Protomaps flavours via `paintRules/labelRules` (what we use) | Standard style JSON from `@protomaps/basemaps` |
| Marker/cluster/popup code | Unchanged | Must be rewritten: divIcon markers, leaflet.markercluster, popups, catchments, search pin, controls, four presets |
| Testing | Works in headless Chromium here **[cloud]** | WebGL needs software GL in CI/headless; more fragile |
| Effort / risk | Done | roughly 1 to 2 weeks of work plus regression risk to the operational map |
Recommendation: stay on Leaflet. Reconsider MapLibre only if the real archive shows unacceptable label quality or pan performance on your laptop. That would need your approval first.

## 7. Themes
Global theme: System / Light / Dark (`src/lib/theme.ts`, switch in the header, drawer, sidebar and Settings). Independent map appearance: Follow app theme (default) / Light / Dark. Both are per-browser preferences. The map style = (resolved map theme) x (preset): Classic and Navigation use the stock Protomaps light/dark flavours; Tactical and Flood Intelligence adjust a few colours of the same flavour. One archive serves all eight combinations **[fixture: all eight rendered]**.

## 8. Local search
PMTiles does not geocode. A separate compact index is built by `scripts/build_search_index.py` from the same PBF: named cities, towns, suburbs, villages, hospitals/clinics, schools, colleges, police and fire stations, airports, railway/metro stations, named lakes/reservoirs, parks/forests and notable landmarks (places of worship only when they have a Wikipedia/Wikidata tag). Roads and buildings are not indexed. Names are normalised (case, accents, punctuation) and stored in gzip shards keyed by the first two characters of a name or of its first words; the browser downloads `index.json` once and then one or two small shards per query, with an in-memory cache limited to 24 shards. Ranking: exact, prefix, word prefix, substring, then place size, then distance to the map centre. Search stays local-first; "Search online instead" remains a separate explicit button that says it sends your text to Nominatim.
Limits: relations (multipolygon areas) are not indexed; way centroids need a disk-backed node index in the temp folder (`--nodes-only` avoids it); non-Latin names are indexed under their own characters. Size is **[estimate]**.
**[fixture]**: the same code path served a fixture index built from real BBMP ward names ("hebb" -> Hebbala via shard `he.json.gz`). **[cloud]**: the builder ran on a tiny synthetic OSM file (nodes, a way with disk-backed locations, temp folder removed).

## 9. Windows commands (PowerShell; not executed in the cloud)
Keep the work folder outside OneDrive. All steps are in `rescuenet-x2\frontend\scripts\windows\regional-gis.ps1`. Open PowerShell in your clone of the repository:
```powershell
cd <your clone>\rescuenet-x2\frontend\scripts\windows
Set-ExecutionPolicy -Scope Process Bypass     # this window only
$Pbf = 'C:\Users\Bhavana\OneDrive\Documents\Flood degi twin rescuenet X\datasets\southern-zone-261124.osm.pbf'

.\regional-gis.ps1 -Step Check     -Pbf $Pbf    # disk, RAM, CPU, tool check, estimates; stops if disk is too small
.\regional-gis.ps1 -Step Setup     -Pbf $Pbf    # portable JDK + Maven + profile jar + Python venv, all under C:\RescueNetGIS
.\regional-gis.ps1 -Step Validate  -Pbf $Pbf    # size, OSMHeader, SHA-256, Geofabrik MD5 (if reachable), bounding box
.\regional-gis.ps1 -Step Benchmark -Pbf $Pbf    # Bengaluru only: measured time and peak memory
.\regional-gis.ps1 -Step Build     -Pbf $Pbf -Approve   # full archive; REFUSES without a prior Benchmark and an explicit -Approve (you accept the resource budget after reading the benchmark)
.\regional-gis.ps1 -Step Verify    -Pbf $Pbf    # header, bounds, layers, one real tile
.\regional-gis.ps1 -Step Search    -Pbf $Pbf    # compact place index -> C:\RescueNetGIS\out\search
.\regional-gis.ps1 -Step Clean     -Pbf $Pbf    # only after Verify passes; the PBF is never touched (add -Tools to drop the JDK/Maven too)
```
Memory/CPU limits are parameters: `-HeapGB 3 -Threads 4` (defaults). Make sure the PBF is "Always keep on this device" in OneDrive before `Validate`.

Serve the archive and start the app (three PowerShell windows):
```powershell
# window 1: tiles + search index (Range requests, localhost only)
.\regional-gis.ps1 -Step Serve
# window 2: backend, exactly as in docs\WINDOWS_LOCAL_GUIDE.md (unchanged)
# window 3: frontend (the default URL already matches; set it only if you changed the port or file name)
cd <your clone>\rescuenet-x2\frontend
$env:VITE_REGIONAL_PMTILES_URL = 'http://127.0.0.1:8077/south-india.pmtiles'
npm run dev
```
Verify in the browser: open Flood Digital Twin, *Style and layers* -> *Base map* -> "Regional offline map (vector archive)"; the chip must read "Offline map: regional vector archive". Then for each of Classic, Tactical, Navigation, Flood Intelligence check roads, buildings (zoom 15+), names, water and parks, and that markers/catchments line up. Test themes: header switch System/Light/Dark and *Map appearance* Follow/Light/Dark independently. Test fallback: stop window 1 and reload; the chip must fall back to the basic local map, nothing breaks. To prove it works with the internet off, disconnect Wi-Fi after the page loads and pan around. Without the archive running, the app behaves exactly as before.

Without Windows, check any archive: `node scripts\pmtiles_inspect.mjs C:\RescueNetGIS\out\south-india.pmtiles`.

## 10. Licensing and Git protection
- OpenStreetMap data: ODbL 1.0, (c) OpenStreetMap contributors. The map attribution (read from the archive metadata, with a built-in fallback) stays visible. A derived tile archive is a Produced Work: keep the attribution; if you ever share the archive or the search index, note that they are derived from OSM. Natural Earth is public domain. Protomaps basemap tooling and styles are BSD-3 (the name "Protomaps" may not be used for modified forks of their tilesets/styles, which we do not distribute).
- `.gitignore` now excludes `*.osm.pbf`, `*.pmtiles`, `*.mbtiles`, `rescuenet-x2/frontend/regional-data/`, `rescuenet-x2/gis-work/` and `datasets/`. Nothing large is committed. Generated provenance (`provenance.json`: source file, size, SHA-256, build date, licence) is written next to the archive.

## 11. What was verified where
| Claim | Status |
|---|---|
| Code path: probe, PMTiles Range reads, vector rendering, theme x preset styles, fallback to basic local map, source chip, coverage notice, regional search, local tile server (Range 206, CORS, no path traversal) | **[fixture]** + **[cloud]** (unit tests: 52 passing; production build OK) |
| Fixture content | Built from the already bundled Natural Earth + BBMP data: no OpenStreetMap data, no residential streets, no buildings. Marked "TEST FIXTURE" in the metadata and the on-map chip |
| Search index builder and OSM layer scripts | **[cloud]** on tiny synthetic OSM XML only |
| PowerShell script | Written, **never executed** (no Windows/PowerShell in the cloud). Run `Check` first |
| Planetiler/Protomaps flags (`--storage`, `--nodemap-storage`, `--bounds`, `--tmpdir`, `--threads`) | Written from memory of the tool's CLI; `Benchmark`/`Build` check `--help-all` and **stop with the missing option named** if one is not listed (nothing is silently dropped) |
| South India extent, feature richness, archive size, build time, peak memory | **[to measure]** on your laptop |
| Real archive rendering in the four presets | **Not verified.** Do not claim full South India rendering until `Verify` and the preset checks above pass |

Remaining blockers: real PBF processing (needs your Windows run), the exact Protomaps profile build requirements at the commit you clone (JDK version), and label density/readability on the real data.
