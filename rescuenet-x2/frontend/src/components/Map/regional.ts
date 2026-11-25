import type L from 'leaflet';
import type { Theme } from './localBasemap';

/** Regional offline basemap: one PMTiles vector tile archive (Protomaps basemap schema, built from an OpenStreetMap extract) served from
 *  this computer. The archive holds the geometry once; light/dark and the four map presets are only different *styles* applied at draw time.
 *  The archive is optional: when it is not configured or not reachable, `probeRegional()` resolves to null and the map keeps working
 *  with the online providers and the small bundled Natural Earth / BBMP map. Only the tiles for the current view are requested (HTTP Range). */
export const REGIONAL_URL: string = (import.meta.env.VITE_REGIONAL_PMTILES_URL as string | undefined) ?? 'http://127.0.0.1:8077/south-india.pmtiles';
export const REGIONAL_SEARCH_URL: string = (import.meta.env.VITE_REGIONAL_SEARCH_URL as string | undefined) ?? REGIONAL_URL.replace(/[^/]*$/, 'search/');
export const DEFAULT_REGIONAL_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors (ODbL), <a href="https://protomaps.com" target="_blank" rel="noreferrer">Protomaps</a> basemap schema';

export interface RegionalInfo {
  url: string; bounds: [number, number, number, number]; minZoom: number; maxZoom: number; center: [number, number, number];
  name: string; attribution: string; isFixture: boolean; built?: string; source?: string;
}

const i32 = (v: DataView, o: number) => v.getInt32(o, true) / 1e7;
const u64 = (v: DataView, o: number) => Number(v.getBigUint64(o, true));

async function range(url: string, start: number, len: number, signal?: AbortSignal): Promise<ArrayBuffer> {
  const r = await fetch(url, { headers: { Range: `bytes=${start}-${start + len - 1}` }, signal });
  if (r.status !== 206 && r.status !== 200) throw new Error(`HTTP ${r.status}`);
  return r.arrayBuffer();
}

/** Reads only the 127-byte PMTiles header (plus the small metadata JSON). Never downloads tiles. */
export async function readRegionalInfo(url: string, timeoutMs = 4000): Promise<RegionalInfo> {
  const ctl = new AbortController(); const t = window.setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const hb = await range(url, 0, 127, ctl.signal);
    if (hb.byteLength < 127) throw new Error('short header');
    const v = new DataView(hb);
    const magic = String.fromCharCode(...new Uint8Array(hb, 0, 7)); if (magic !== 'PMTiles' || v.getUint8(7) !== 3) throw new Error('not a PMTiles v3 archive');
    const info: RegionalInfo = {
      url, minZoom: v.getUint8(100), maxZoom: v.getUint8(101), bounds: [i32(v, 102), i32(v, 106), i32(v, 110), i32(v, 114)], center: [i32(v, 119), i32(v, 123), v.getUint8(118)],
      name: 'Regional vector archive', attribution: DEFAULT_REGIONAL_ATTRIBUTION, isFixture: false,
    };
    try {
      const mOff = u64(v, 24), mLen = u64(v, 32), comp = v.getUint8(97);
      if (mLen > 0 && mLen < 262144) {
        let buf = await range(url, mOff, mLen, ctl.signal);
        if (comp === 2 && typeof DecompressionStream !== 'undefined') buf = await new Response(new Response(buf).body!.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
        const m = JSON.parse(new TextDecoder().decode(buf));
        if (m.name) info.name = String(m.name); if (m.attribution) info.attribution = String(m.attribution); info.isFixture = m.type === 'fixture';
        info.built = m.rescuenet_built; info.source = m.rescuenet_source;
      }
    } catch { /* metadata is optional */ }
    return info;
  } finally { window.clearTimeout(t); }
}

let probe: Promise<RegionalInfo | null> | null = null;
export function probeRegional(url: string = REGIONAL_URL): Promise<RegionalInfo | null> {
  if (!probe) probe = readRegionalInfo(url).catch(() => null);
  return probe;
}
export function resetRegionalProbe() { probe = null; }

export const inBounds = (b: RegionalInfo['bounds'], lat: number, lng: number) => lng >= b[0] && lng <= b[2] && lat >= b[1] && lat <= b[3];

/** One style per preset and theme, derived from the same Protomaps light/dark flavours: the data is shared, only colours change. */
async function flavorFor(theme: Theme, preset: string) {
  const { namedFlavor } = await import('@protomaps/basemaps');
  const f = { ...namedFlavor(theme) } as Record<string, any>;
  if (theme === 'dark') {
    if (preset === 'tactical') Object.assign(f, { background: '#0a1220', earth: '#0d1626', water: '#0a2a40', buildings: '#1b2740', minor_a: '#2a3a58', minor_b: '#2a3a58', major: '#3d5278', highway: '#d9a43a', highway_casing_early: '#0a1220' });
    if (preset === 'flood') Object.assign(f, { earth: '#101a2c', water: '#124b73', park_a: '#12281f', park_b: '#12281f', buildings: '#18233a' });
  } else {
    if (preset === 'tactical') Object.assign(f, { earth: '#e3e7ee', background: '#d6dbe4', water: '#a9c6e0', buildings: '#cfd5df' });
    if (preset === 'flood') Object.assign(f, { earth: '#eef0ec', water: '#8fc1e8', park_a: '#d7e8d2', park_b: '#d7e8d2' });
  }
  return f as any;
}

export interface RegionalHandle { remove(): void; layer: L.Layer }
export async function drawRegional(map: L.Map, info: RegionalInfo, theme: Theme, preset: string, onError?: () => void): Promise<RegionalHandle> {
  const [{ leafletLayer, paintRules, labelRules }, flavor] = await Promise.all([import('protomaps-leaflet'), flavorFor(theme, preset)]);
  const layer = leafletLayer({
    url: info.url, paintRules: paintRules(flavor), labelRules: labelRules(flavor, 'en'), backgroundColor: flavor.background, attribution: info.attribution,
    maxDataZoom: info.maxZoom, maxNativeZoom: info.maxZoom, maxZoom: 19, tileSize: 256,
  } as any) as unknown as L.GridLayer;
  let errs = 0; layer.on('tileerror', () => { errs += 1; if (errs >= 3) onError?.(); });
  layer.addTo(map); layer.bringToBack();
  return { layer, remove: () => { map.removeLayer(layer); } };
}
