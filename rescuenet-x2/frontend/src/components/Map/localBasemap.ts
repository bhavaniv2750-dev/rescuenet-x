import L from 'leaflet';

/** Local, offline geographical basemap. Everything drawn here comes from files in /basemap (see docs/frontend/LOCAL_BASEMAP.md for sources and
 *  licences): Natural Earth (public domain) for major roads, railways, rivers, lakes, towns, airports, urban areas and state boundaries, and the
 *  243 BBMP ward polygons with their names (CC BY-SA 2.5 India). Optional street-level OpenStreetMap layers (osm_*.json) are drawn when present.
 *  Nothing is generated or invented; no network request leaves the server that serves the app. */
type FC = { type: 'FeatureCollection'; features: any[] };
export interface LocalData { wards: FC; roads: FC; rail: FC; rivers: FC; lakes: FC; places: FC; airports: FC; urban: FC; states: FC; manifest: any; osm: Record<string, FC> }
export const LOCAL_ATTRIBUTION = 'Offline map data: <a href="https://www.naturalearthdata.com/" target="_blank" rel="noreferrer">Natural Earth</a> (public domain), BBMP wards 2022 via <a href="https://github.com/datameet/Municipal_Spatial_Data" target="_blank" rel="noreferrer">DataMeet</a> (CC BY-SA 2.5 India)';
const OSM_LAYERS = ['osm_roads', 'osm_water', 'osm_parks', 'osm_places', 'osm_buildings', 'osm_landmarks'];

let cache: Promise<LocalData> | null = null;
const get = async (name: string): Promise<any> => { const r = await fetch(`${import.meta.env.BASE_URL}basemap/${name}.json`); if (!r.ok) throw new Error(`${name}: ${r.status}`); return r.json(); };
const opt = async (name: string): Promise<FC | null> => { try { const r = await fetch(`${import.meta.env.BASE_URL}basemap/${name}.json`); const ct = r.headers.get('content-type') || ''; return r.ok && ct.includes('json') ? await r.json() : null; } catch { return null; } };
/** Loaded once, on demand (about 0.3 MB for the bundled set). */
export function loadLocalBasemap(): Promise<LocalData> {
  if (!cache) {
    cache = (async () => {
      const [wards, roads, rail, rivers, lakes, places, airports, urban, states, manifest] = await Promise.all(['wards', 'roads', 'rail', 'rivers', 'lakes', 'places', 'airports', 'urban', 'states', 'manifest'].map(get));
      const osm: Record<string, FC> = {};
      for (const n of OSM_LAYERS) { const d = await opt(n); if (d && d.features?.length) osm[n] = d; }
      return { wards, roads, rail, rivers, lakes, places, airports, urban, states, manifest, osm } as LocalData;
    })();
    cache.catch(() => { cache = null; });
  }
  return cache;
}

export type Theme = 'dark' | 'light';
export interface Palette { land: string; state: string; stateLine: string; urban: string; lake: string; river: string; ward: string; wardLine: string; roadCase: string; hwy: string; road2: string; rail: string; label: string; halo: string; park: string; building: string }
const DARK: Palette = { land: '#0e1a2b', state: '#0e1a2b', stateLine: '#3a4f6e', urban: '#15263d', lake: '#1d4f7a', river: '#2f86c8', ward: 'rgba(120,160,210,0.045)', wardLine: '#34507a', roadCase: '#08101c', hwy: '#d6a84a', road2: '#7f93b3', rail: '#5c6f8c', label: '#a9bbd3', halo: '#0b1424', park: '#173a2e', building: '#22334d' };
const LIGHT: Palette = { land: '#eef0ea', state: '#eef0ea', stateLine: '#a7b0bb', urban: '#e3e6de', lake: '#a9d3e6', river: '#8cc0dc', ward: 'rgba(70,100,140,0.035)', wardLine: '#a9b4c1', roadCase: '#ffffff', hwy: '#f1b04a', road2: '#f6cf8b', rail: '#9aa3ad', label: '#4a5463', halo: '#ffffff', park: '#cfe6c4', building: '#d9d6cf' };
export const paletteFor = (theme: Theme, preset: string): Palette => {
  const p = { ...(theme === 'dark' ? DARK : LIGHT) };
  if (preset === 'tactical') { p.wardLine = '#35527a'; p.ward = 'rgba(80,170,220,0.05)'; }
  if (preset === 'flood') { p.wardLine = theme === 'dark' ? '#2c4262' : '#c4ccd6'; p.river = theme === 'dark' ? '#38a3e8' : '#6fb3da'; p.lake = theme === 'dark' ? '#215f93' : '#8ec7e3'; }
  return p;
};

const ringCentroid = (ring: number[][]): [number, number] => {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) { const f = ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1]; a += f; cx += (ring[j][0] + ring[i][0]) * f; cy += (ring[j][1] + ring[i][1]) * f; }
  if (Math.abs(a) < 1e-12) return [ring[0][1], ring[0][0]];
  return [cy / (3 * a), cx / (3 * a)];
};
const geomCentroid = (g: any): [number, number] | null => {
  if (!g) return null;
  if (g.type === 'Polygon') return ringCentroid(g.coordinates[0]);
  if (g.type === 'MultiPolygon') { const big = g.coordinates.map((p: number[][][]) => p[0]).sort((a: number[][], b: number[][]) => b.length - a.length)[0]; return ringCentroid(big); }
  if (g.type === 'Point') return [g.coordinates[1], g.coordinates[0]];
  return null;
};

export interface LocalHandle { remove(): void }
/** Draw the local basemap into the map. Detail depends on zoom: ward polygons from zoom 9, ward names from zoom 12 (collision-aware, capped), towns always. */
export function drawLocal(map: L.Map, d: LocalData, theme: Theme, preset: string): LocalHandle {
  const pal = paletteFor(theme, preset);
  const mk = (name: string, z: number, ev = 'none') => { if (!map.getPane(name)) { const p = map.createPane(name); p.style.zIndex = String(z); p.style.pointerEvents = ev; } return map.getPane(name)!; };
  mk('localbase', 205); mk('locallabels', 455);
  const canvas = L.canvas({ pane: 'localbase', padding: 0.4 });
  const group = L.layerGroup().addTo(map);
  const add = (data: FC | undefined, style: L.PathOptions | ((f: any) => L.PathOptions), filter?: (f: any) => boolean) => { if (data?.features.length) L.geoJSON(data as any, { renderer: canvas, pane: 'localbase', interactive: false, style: style as any, filter } as any).addTo(group); };

  add(d.states, { color: pal.stateLine, weight: 1, dashArray: '4 4', fillColor: pal.state, fillOpacity: 0.0 });
  add(d.urban, { stroke: false, fillColor: pal.urban, fillOpacity: 1 });
  if (d.osm.osm_parks) add(d.osm.osm_parks, { stroke: false, fillColor: pal.park, fillOpacity: 0.9 });
  add(d.lakes, { color: pal.lake, weight: 0.5, fillColor: pal.lake, fillOpacity: 0.95 });
  if (d.osm.osm_water) add(d.osm.osm_water, { color: pal.lake, weight: 0.5, fillColor: pal.lake, fillOpacity: 0.95 });
  if (d.osm.osm_buildings) add(d.osm.osm_buildings, { stroke: false, fillColor: pal.building, fillOpacity: 0.8 });
  add(d.rail, { color: pal.rail, weight: 1, dashArray: '5 4', opacity: 0.8 });
  add(d.rivers, { color: pal.river, weight: 2, opacity: 0.95 });
  const hw = (f: any) => /highway|major/i.test(String(f.properties.type || ''));
  add(d.roads, (f) => ({ color: pal.roadCase, weight: hw(f) ? 5 : 4, opacity: 1, lineCap: 'round' }));
  add(d.roads, (f) => ({ color: hw(f) ? pal.hwy : pal.road2, weight: hw(f) ? 3 : 2, opacity: 1, lineCap: 'round' }));
  if (d.osm.osm_roads) {
    add(d.osm.osm_roads, (f) => ({ color: pal.roadCase, weight: ['motorway', 'trunk', 'primary'].includes(f.properties.highway) ? 5 : 3, opacity: 1 }));
    add(d.osm.osm_roads, (f) => ({ color: ['motorway', 'trunk', 'primary'].includes(f.properties.highway) ? pal.hwy : pal.road2, weight: ['motorway', 'trunk', 'primary'].includes(f.properties.highway) ? 3 : 1.5, opacity: 1 }));
  }
  // ward polygons: Bengaluru administrative boundaries (zoom 9 and closer)
  const wardLayer = L.geoJSON(d.wards as any, { renderer: canvas, pane: 'localbase', interactive: false, style: () => ({ color: pal.wardLine, weight: 0.8, fillColor: theme === 'dark' ? '#78a0d2' : '#466490', fillOpacity: 0.07 }) } as any);
  const labels = L.layerGroup().addTo(map);
  const wardPts = d.wards.features.map((f) => ({ c: geomCentroid(f.geometry), n: String(f.properties.name || '').replace(/\s+Ward$/i, '') })).filter((w) => w.c && w.n) as { c: [number, number]; n: string }[];
  const places = [...d.places.features, ...(d.osm.osm_places?.features ?? [])].map((f) => ({ c: geomCentroid(f.geometry), n: String(f.properties.name || ''), pop: Number(f.properties.pop_max || 0) })).filter((p) => p.c && p.n).sort((a, b) => b.pop - a.pop) as { c: [number, number]; n: string; pop: number }[];
  const air = d.airports.features.map((f) => ({ c: geomCentroid(f.geometry), n: String(f.properties.name || '') })).filter((a) => a.c) as { c: [number, number]; n: string }[];

  const update = () => {
    const z = map.getZoom(); const showWards = z >= 9;
    if (showWards && !group.hasLayer(wardLayer)) wardLayer.addTo(group); if (!showWards && group.hasLayer(wardLayer)) group.removeLayer(wardLayer);
    labels.clearLayers();
    const b = map.getBounds().pad(0.02); const boxes: { x: number; y: number; w: number; h: number }[] = []; let n = 0;
    const put = (c: [number, number], text: string, cls: string, glyph = '') => {
      if (n > 90 || !b.contains(c)) return; const p = map.latLngToContainerPoint(c);
      const w = (text.length + glyph.length) * (cls === 'place' ? 7.4 : 6.1) + 8, h = 15; const r = { x: p.x - w / 2, y: p.y - h / 2, w, h };
      if (boxes.some((o) => r.x < o.x + o.w && r.x + r.w > o.x && r.y < o.y + o.h && r.y + r.h > o.y)) return;   // collision-aware: skip labels that would overlap
      boxes.push(r); n += 1;
      L.marker(c, { pane: 'locallabels', interactive: false, keyboard: false, icon: L.divIcon({ className: `rn-geo-label ${cls}`, html: `<span style="--lab:${pal.label};--halo:${pal.halo}">${glyph}${text.replace(/[<>&]/g, '')}</span>`, iconSize: [0, 0] }) }).addTo(labels);
    };
    places.forEach((p) => { if (z >= 7 || p.pop > 500000) put(p.c, p.n, 'place'); });
    air.forEach((a) => { if (z >= 9) put(a.c, a.n.replace(/ International| Airport|\(.*?\)/g, '').trim() || a.n, 'air', '✈ '); });
    if (z >= 12) wardPts.forEach((w) => put(w.c, w.n, 'ward'));
  };
  map.on('moveend zoomend', update); update();
  return { remove() { map.off('moveend zoomend', update); map.removeLayer(group); map.removeLayer(labels); } };
}

export interface LocalHit { name: string; kind: string; lat: number; lng: number }
/** Basic local place search over the bundled names (wards, towns, airports and any OSM places). Matches by prefix first, then substring. */
export function searchLocal(d: LocalData, q: string, limit = 8): LocalHit[] {
  const s = q.trim().toLowerCase(); if (s.length < 2) return [];
  const all: LocalHit[] = [];
  const push = (fc: FC | undefined, kind: string, nameOf: (p: any) => string) => fc?.features.forEach((f) => { const c = geomCentroid(f.geometry); const name = nameOf(f.properties); if (c && name) all.push({ name, kind, lat: c[0], lng: c[1] }); });
  push(d.wards, 'BBMP ward', (p) => `${String(p.name || '')}${p.no ? ` (ward ${p.no})` : ''}`);
  push(d.places, 'town or city', (p) => p.name); push(d.airports, 'airport', (p) => p.name); push(d.osm.osm_places, 'place (OpenStreetMap)', (p) => p.name); push(d.osm.osm_landmarks, 'landmark (OpenStreetMap)', (p) => p.name);
  const pre = all.filter((h) => h.name.toLowerCase().startsWith(s)); const sub = all.filter((h) => !h.name.toLowerCase().startsWith(s) && h.name.toLowerCase().includes(s));
  return [...pre, ...sub].slice(0, limit);
}
