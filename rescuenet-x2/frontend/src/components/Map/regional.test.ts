import { describe, it, expect, vi, afterEach } from 'vitest';
import { gzipSync } from 'node:zlib';
import { DecompressionStream as NodeDS } from 'node:stream/web';
import { inBounds, readRegionalInfo } from './regional';
import { normalise, shardKey } from './regionalSearch';

/** Builds a PMTiles v3 header (127 bytes) plus a metadata block, as the real archive would have. */
function archive(meta: object, bounds: [number, number, number, number], zooms: [number, number]) {
  const metaBytes = gzipSync(Buffer.from(JSON.stringify(meta)));
  const buf = Buffer.alloc(127 + metaBytes.length);
  buf.write('PMTiles', 0, 'ascii'); buf.writeUInt8(3, 7);
  buf.writeBigUInt64LE(BigInt(127), 24); buf.writeBigUInt64LE(BigInt(metaBytes.length), 32); buf.writeUInt8(2, 97);
  buf.writeUInt8(zooms[0], 100); buf.writeUInt8(zooms[1], 101);
  [bounds[0], bounds[1], bounds[2], bounds[3]].forEach((v, i) => buf.writeInt32LE(Math.round(v * 1e7), 102 + i * 4));
  buf.writeUInt8(10, 118); buf.writeInt32LE(Math.round(77.59e7), 119); buf.writeInt32LE(Math.round(12.97e7), 123);
  metaBytes.copy(buf, 127); return buf;
}
const serve = (buf: Buffer) => { withDS(); vi.stubGlobal('fetch', vi.fn(async (_u: string, init: any) => {
  const m = /bytes=(\d+)-(\d+)/.exec(init?.headers?.Range ?? '')!; const s = Number(m[1]), e = Number(m[2]);
  const part = buf.subarray(s, e + 1); return new Response(part, { status: 206 });
})); };
afterEach(() => vi.unstubAllGlobals());
const withDS = () => vi.stubGlobal('DecompressionStream', NodeDS);

describe('regional archive header', () => {
  it('reads bounds, zooms and metadata with Range requests only', async () => {
    serve(archive({ name: 'South India', attribution: '(c) OSM', type: 'baselayer' }, [74.0, 8.0, 80.5, 19.9], [0, 15]));
    const i = await readRegionalInfo('http://x/a.pmtiles');
    expect(i.bounds[0]).toBeCloseTo(74.0, 3); expect(i.bounds[3]).toBeCloseTo(19.9, 3); expect(i.maxZoom).toBe(15); expect(i.name).toBe('South India'); expect(i.isFixture).toBe(false);
    expect((fetch as any).mock.calls.every((c: any[]) => /^bytes=\d+-\d+$/.test(c[1].headers.Range))).toBe(true);
  });
  it('marks a test fixture as such', async () => {
    serve(archive({ name: 'fixture', type: 'fixture' }, [74, 11.5, 78.8, 18.6], [0, 13])); expect((await readRegionalInfo('http://x/a.pmtiles')).isFixture).toBe(true);
  });
  it('rejects things that are not a PMTiles archive (so the basic local map is used)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(Buffer.alloc(127, 1), { status: 206 }))); await expect(readRegionalInfo('http://x/a')).rejects.toThrow();
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 404 }))); await expect(readRegionalInfo('http://x/a')).rejects.toThrow();
  });
  it('detects when a point is outside the archive coverage', () => {
    const b: [number, number, number, number] = [74, 8, 80.5, 19.9]; expect(inBounds(b, 12.97, 77.59)).toBe(true); expect(inBounds(b, 28.6, 77.2)).toBe(false);
  });
});

describe('regional search keys (must match scripts/search_index_lib.py)', () => {
  it('normalises case, accents and punctuation', () => {
    expect(normalise('Café Düsseldorf')).toBe('cafe dusseldorf'); expect(normalise('Sri  Venkateshwara-Temple')).toBe('sri venkateshwara temple');
  });
  it('derives the same shard keys as the Python index builder', () => {
    expect(shardKey('koramangala')).toBe('ko'); expect(shardKey('ಬೆಂಗಳೂರು')).toBe('~cac~cc6'); expect(shardKey('a')).toBe('');
  });
});
