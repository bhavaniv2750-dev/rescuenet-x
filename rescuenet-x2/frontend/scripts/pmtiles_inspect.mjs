// Prints the header and metadata of a PMTiles archive and fetches one tile to prove it decodes. Reads only the header/directories
// (HTTP Range or local file), never the whole archive.   node scripts/pmtiles_inspect.mjs <file.pmtiles | http://...> 
import { PMTiles, FetchSource } from 'pmtiles';
import fs from 'node:fs';

class FileSource {
  constructor(p) { this.p = p; this.fd = fs.openSync(p, 'r'); }
  getKey() { return this.p; }
  async getBytes(offset, length) { const b = Buffer.alloc(length); const n = fs.readSync(this.fd, b, 0, length, offset); return { data: b.buffer.slice(b.byteOffset, b.byteOffset + n) }; }
}
const arg = process.argv[2];
if (!arg) { console.error('usage: node scripts/pmtiles_inspect.mjs <file.pmtiles | url>'); process.exit(2); }
const p = new PMTiles(/^https?:/.test(arg) ? new FetchSource(arg) : new FileSource(arg));
const h = await p.getHeader();
const e7 = (v) => (v).toFixed(4);
console.log(JSON.stringify({ tileType: h.tileType, minZoom: h.minZoom, maxZoom: h.maxZoom, bounds: [e7(h.minLon), e7(h.minLat), e7(h.maxLon), e7(h.maxLat)], center: [e7(h.centerLon), e7(h.centerLat), h.centerZoom], tileEntries: h.numTileEntries, tileContents: h.numTileContents, compression: h.tileCompression }, null, 1));
const m = await p.getMetadata(); console.log('metadata:', JSON.stringify({ name: m.name, type: m.type, version: m.version, attribution: m.attribution, layers: (m.vector_layers || []).map((l) => l.id) }, null, 1));
const z = Math.min(10, h.maxZoom); const n = 2 ** z; const x = Math.floor(((h.centerLon + 180) / 360) * n); const lat = (h.centerLat * Math.PI) / 180; const y = Math.floor(((1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2) * n);
const t = await p.getZxy(z, x, y); console.log(`center tile ${z}/${x}/${y}:`, t ? `${t.data.byteLength} bytes (decodes as ${h.tileCompression === 2 ? 'gzip' : 'raw'} MVT)` : 'MISSING');
