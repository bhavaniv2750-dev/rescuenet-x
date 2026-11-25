# GIS map refinement

Scope: visual refinement of the existing Leaflet maps (Overview, Flood Digital Twin, report location picker). No new data, no MapLibre, no 3D, no offline downloads, no routes, heatmaps or inundation polygons.

* **Basemaps** (`src/components/Map/basemaps.ts`): dark (CARTO Dark Matter) by default in the operations console, light (CARTO Positron) in the public portal, and the existing OpenStreetMap standard tiles; a selector in the layers panel switches between them and the choice is remembered in this browser only.
* **Licensing, stated as understood and NOT re-verified online** (this environment cannot reach the providers): CARTO basemaps need no API key and are free for non-commercial use with attribution ("(c) OpenStreetMap contributors (c) CARTO", shown by the attribution control); the underlying data is OpenStreetMap (ODbL). OpenStreetMap tiles follow the OSMF tile usage policy (light use, attribution, no bulk download or offline caching). This project is an academic, non-commercial prototype. Before any commercial or heavy-traffic use the providers' current terms must be checked and, if needed, a different tile source or self-hosting chosen.
* **Markers** (`markers.ts`): shape by kind (circle incidents, rounded square squads, square facilities with a letter per type, diamond gauge stations); incident colour and glyph both follow severity (`!!`, `!`, triangle, dot); every marker has a text title. Volunteers are not drawn because the data has no coordinates.
* **Popups** show only backend fields, every value HTML-escaped (the previous popups inserted raw text); empty fields are omitted; gauge popups say the live reading is not available.
* **Clustering**: `leaflet.markercluster` (MIT) for incidents, facilities and gauges; squads and alert circles stay unclustered.
* **Controls**: compact collapsible "Layers and map" panel, collapsible legend that lists only kinds present, zoom, recenter, full screen (CSS fallback), 44 px touch targets on phones.
* **States**: "Loading map" chip, and a notice when tiles cannot be fetched (overlays still draw; the background is missing). In the evidence screenshots the notice is visible because the capture environment has no access to the tile servers, so real basemap imagery is not shown there.
* **Tests**: `map.test.ts` (no API key in any basemap URL, attribution present, popup escaping, distinct glyphs/colours). Fixed during the work: markercluster v2 exports `MarkerClusterGroup` (not `L.markerClusterGroup`), and the map needs `maxZoom` at creation.

## Selectable visual presets (comparison round)
Choose in the map's "Style and layers" panel (remembered in this browser only; the default stays **Classic** until you decide). All presets draw the same backend records and coordinates, the same clusters, popups/cards and overlays; only presentation changes. The attached reference image was not visible to the assistant (only the text of the request arrived), so Tactical follows the written description (dark urban basemap, teardrop markers, glow, alert rings, floating labels), not the picture. Please compare against your reference.

| Preset | Basemap (auto) | Markers | Extras |
|---|---|---|---|
| Classic | CARTO Dark Matter (console) / Positron (public) | compact round/square pins with letters (current) | none |
| Tactical | CARTO Dark Matter, desaturated and dimmed | dark teardrops with coloured outline, tight glow, icon inside; incident severity glyph | alert rings on CRITICAL incidents only (static under reduced motion), floating labels for critical/selected incidents, popups |
| Navigation | CARTO Voyager (OSM-based road map; dark variant switch) | flat location pins with white centre | place search (Nominatim, on button press), information card instead of popup, my-location |
| Flood Intelligence | CARTO Voyager, toned down | category shapes: circle incident, hexagon squad, white square + cross hospital, house shelter, tent camp, diamond gauge | translucent catchments, amber dashed alert areas, rings + labels for critical, information card, search |

Common to all: zoom-aware marker size, clustering, hover and selected states, "Fit all data", "Recenter on Bengaluru" (default view), "Show my location" (your own position, shown only on your screen), full screen, collapsible style/layer panel and legend (legend swatches are drawn with the same marker markup), smooth fly-to transitions.

### Honest comparison (judged from the screenshots in `docs/evidence/GIS/offline/`, captured with all external tile hosts blocked; see LOCAL_BASEMAP.md)
* **Readability.** Navigation and Flood Intelligence have the highest contrast of pins against a light road map and the most familiar look; Tactical has the strongest incident emphasis in a dark room but dark pins on a dark map rely on the coloured outline; Classic is the most compact and least distinctive. Only Flood Intelligence and Navigation differ by shape per category (accessibility); Tactical differs by icon and severity glyph.
* **Performance.** Same markers, same clustering: switching style rebuilds the marker layers in about 80 to 120 ms with 17 incidents, 5 squads, 9 facilities and 23 gauges (scripted measurement, `browser_run.txt`). Rings use one CSS animation each and are limited to critical incidents. No measurable difference between presets at this data size; larger datasets were not tested.
* **Usability.** Navigation and Flood add a search box and an information card (better for touch, no popup tail covering pins). Tactical keeps popups and adds floating labels, which can crowd at medium zoom (only critical/selected incidents are labelled to limit this). On phones the panels are collapsed by default and controls are 44 px.

### Basemap reliability (investigated)
The capture environment's network proxy blocks both `tile.openstreetmap.org` and `*.basemaps.cartocdn.com` (HTTP 403 on the CONNECT tunnel), so no real tile could be loaded here; the application detects this, keeps drawing all data at true positions and shows a "base map could not be loaded" notice. This is an environment restriction, not a Leaflet defect, and the code was not changed to hide it. No substitute imagery is drawn. Screenshots therefore show the preset backgrounds without street detail; roads, labels and buildings can only be judged on your machine.
**Verify on Windows:** start the app as in `docs/WINDOWS_LOCAL_GUIDE.md`, open Flood Digital Twin, pick each style, and confirm tiles appear for Dark, Light, Voyager and Streets. If a provider is blocked on your network, choose another Base map or check the browser's network tab for the tile host. Building footprints appear only if the provider's tiles draw them at high zoom (Dark Matter/Voyager show buildings only at the largest zooms); the app does not draw its own.
Place search uses the public Nominatim service only when the Search button is pressed (their policy forbids autocomplete and heavy use; text typed is sent to them). It could not be tested here (blocked); it fails with a clear message.

### Limits and deferred
No traffic, no routing/ETA, no building layer of our own, no inundation or heatmap layers (nothing supports them), no volunteers (no coordinates), no MapLibre/vector tiles, no offline maps. A locally hosted tile source or vector tiles would be the next step for production use.


## Update: local offline basemap
The blank-background problem is resolved by an automatic fallback chain (configured online map, secondary online map, locally served geography, explicit unavailable state). See [LOCAL_BASEMAP.md](LOCAL_BASEMAP.md). Older screenshots that showed a blank background were removed; current evidence is in `docs/evidence/GIS/offline/`.
