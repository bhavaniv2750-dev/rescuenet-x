import { REGIONAL_SEARCH_URL } from './regional';
import type { LocalHit } from './localBasemap';

/** Offline place search over the regional archive's companion index (see scripts/build_search_index.py). PMTiles does not provide geocoding, so a
 *  separate compact index is used: sharded by the first two letters, gzip, loaded lazily (one or two small files per query) and cached in memory (bounded). */
export const KIND_LABEL: Record<string, string> = { c: 'City', t: 'Town', v: 'Village', s: 'Neighbourhood', o: 'Locality', h: 'Hospital / clinic', e: 'School', u: 'College / university', p: 'Police station', f: 'Fire station', b: 'Bus station', a: 'Airport', r: 'Railway / metro station', w: 'Lake / reservoir', k: 'Park / forest', l: 'Landmark' };
const RANK: Record<string, number> = { c: 0, t: 1, s: 2, v: 3, o: 3, a: 2, h: 4, u: 4, r: 4, l: 4, w: 5, k: 5, e: 6, p: 6, f: 6, b: 6 };

export const normalise = (s: string): string =>
  s.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[\s\-_.,;:/\\()'"]+/g, ' ').trim();
const ch = (c: string) => (/[a-z0-9]/.test(c) ? c : '~' + c.codePointAt(0)!.toString(16));
export const shardKey = (norm: string): string => { const cs = Array.from(norm.replace(/ /g, '')).slice(0, 2); return cs.length === 2 ? cs.map(ch).join('') : ''; };

type Rec = [string, string, number, number, string?];
const MAX_CACHED_SHARDS = 24;
const cache = new Map<string, Rec[]>();
let manifest: Promise<{ shards: Record<string, number>; count: number; built: string; source: string } | null> | null = null;
const base = () => (REGIONAL_SEARCH_URL.endsWith('/') ? REGIONAL_SEARCH_URL : REGIONAL_SEARCH_URL + '/');

export function resetRegionalSearch() { cache.clear(); manifest = null; }

export function regionalSearchInfo() {
  if (!manifest) manifest = fetch(base() + 'index.json').then((r) => (r.ok ? r.json() : null)).catch(() => null);
  return manifest;
}

async function shard(key: string): Promise<Rec[]> {
  const hit = cache.get(key); if (hit) { cache.delete(key); cache.set(key, hit); return hit; }   // LRU touch
  const r = await fetch(`${base()}${key}.json.gz`); if (!r.ok) return [];
  const buf = await r.arrayBuffer();
  const text = typeof DecompressionStream !== 'undefined' && new Uint8Array(buf)[0] === 0x1f
    ? await new Response(new Response(buf).body!.pipeThrough(new DecompressionStream('gzip'))).text() : new TextDecoder().decode(buf);
  const recs = JSON.parse(text) as Rec[];
  cache.set(key, recs); while (cache.size > MAX_CACHED_SHARDS) cache.delete(cache.keys().next().value as string);
  return recs;
}

/** Returns null when no regional index is available (callers then use the basic local search). Results are ranked: exact, prefix, word prefix, substring; then place size; then distance to `near`. */
export async function searchRegional(q: string, near?: [number, number], limit = 8): Promise<LocalHit[] | null> {
  const m = await regionalSearchInfo(); if (!m) return null;
  const nq = normalise(q); const keys = new Set<string>(); const k0 = shardKey(nq); if (k0) keys.add(k0);
  for (const w of nq.split(' ').slice(1, 3)) { const k = shardKey(w); if (k && m.shards[k]) keys.add(k); }
  if (!k0 || !m.shards[k0]) { if (!nq.split(' ').some((w) => m.shards[shardKey(w)])) return []; }
  const seen = new Set<string>(); const scored: { r: Rec; s: number; d: number }[] = [];
  for (const k of keys) {
    if (!m.shards[k]) continue;
    for (const r of await shard(k)) {
      const id = `${r[0]}|${r[2]}|${r[3]}`; if (seen.has(id)) continue;
      const n = normalise(r[0]); const alt = r[4] ? normalise(r[4]) : '';
      const s = n === nq || alt === nq ? 0 : n.startsWith(nq) || alt.startsWith(nq) ? 1 : n.split(' ').some((w) => w.startsWith(nq)) ? 2 : n.includes(nq) || alt.includes(nq) ? 3 : -1;
      if (s < 0) continue; seen.add(id);
      scored.push({ r, s: s * 10 + (RANK[r[1]] ?? 6), d: near ? Math.hypot(r[2] - near[0], r[3] - near[1]) : 0 });
    }
  }
  scored.sort((a, b) => a.s - b.s || a.d - b.d || a.r[0].localeCompare(b.r[0]));
  return scored.slice(0, limit).map(({ r }) => ({ name: r[0], kind: KIND_LABEL[r[1]] ?? 'Place', lat: r[2], lng: r[3] }));
}
