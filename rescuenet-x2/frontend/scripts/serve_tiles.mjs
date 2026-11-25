// Minimal local static server for PMTiles archives and the search index, with HTTP Range support (PMTiles needs it).
// Binds to 127.0.0.1 only, serves only *.pmtiles / *.json / *.json.gz from one directory, no directory listing, read-only.
//   node scripts/serve_tiles.mjs [dir=regional-data] [port=8077]
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const dir = path.resolve(process.argv[2] || 'regional-data');
const port = Number(process.argv[3] || 8077);
const TYPES = { '.pmtiles': 'application/octet-stream', '.json': 'application/json', '.gz': 'application/gzip' };
const okOrigin = (o) => !!o && /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(o);

const server = http.createServer((req, res) => {
  const origin = req.headers.origin;
  if (okOrigin(origin)) { res.setHeader('Access-Control-Allow-Origin', origin); res.setHeader('Vary', 'Origin'); }
  res.setHeader('Access-Control-Expose-Headers', 'Content-Range, Accept-Ranges, Content-Length, ETag');
  res.setHeader('Access-Control-Allow-Headers', 'Range, If-Match, If-None-Match');
  res.setHeader('Accept-Ranges', 'bytes');
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }
  if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405); return res.end(); }
  const rel = decodeURIComponent((req.url || '/').split('?')[0]).replace(/^\/+/, '');
  const file = path.resolve(dir, rel);
  const ext = path.extname(file).toLowerCase();
  if (!file.startsWith(dir + path.sep) || !TYPES[ext]) { res.writeHead(404); return res.end('not found'); }
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404); return res.end('not found'); }
    const etag = `"${st.size}-${Math.floor(st.mtimeMs)}"`;
    const headers = { 'Content-Type': TYPES[ext], ETag: etag, 'Cache-Control': 'public, max-age=3600' };
    const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || '');
    let start = 0, end = st.size - 1, status = 200;
    if (m) {
      if (m[1] === '' && m[2] === '') { res.writeHead(416); return res.end(); }
      if (m[1] === '') { start = Math.max(0, st.size - Number(m[2])); } else { start = Number(m[1]); if (m[2] !== '') end = Math.min(end, Number(m[2])); }
      if (start > end || start >= st.size) { res.writeHead(416, { 'Content-Range': `bytes */${st.size}` }); return res.end(); }
      status = 206; headers['Content-Range'] = `bytes ${start}-${end}/${st.size}`;
    }
    headers['Content-Length'] = end - start + 1;
    res.writeHead(status, headers);
    if (req.method === 'HEAD') return res.end();
    fs.createReadStream(file, { start, end }).pipe(res);
  });
});
server.listen(port, '127.0.0.1', () => console.log(`Serving ${dir} at http://127.0.0.1:${port}/ (Range requests supported). Ctrl+C to stop.`));
