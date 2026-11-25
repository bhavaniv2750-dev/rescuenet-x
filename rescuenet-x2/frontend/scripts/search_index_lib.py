"""Compact, sharded, gzip place-name index used by the regional offline search (shared by build_search_index.py and the test fixture).
Layout (all under one directory, served next to the .pmtiles archive):
  index.json          {"version":1,"built":..,"count":N,"shards":{"ko":123,...},"source":..,"licence":..}
  <key>.json.gz       [[name, kind, lat, lng, alt?], ...]   key = first two normalised characters of a name or of one of its first words
The browser loads index.json once and then only the one or two small shards a query needs. Keep normalise()/shard_key() identical to src/components/Map/regionalSearch.ts."""
import gzip, json, re, unicodedata
from pathlib import Path

def normalise(s: str) -> str:
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r'[\s\-_.,;:/\\()\'"]+', ' ', s)
    return s.strip()

def _ch(c: str) -> str:
    return c if ('a' <= c <= 'z' or '0' <= c <= '9') else '~%x' % ord(c)

def shard_key(norm: str) -> str:
    chars = [c for c in norm if c != ' '][:2]
    return ''.join(_ch(c) for c in chars) if len(chars) == 2 else ''

def keys_for(name: str, max_words: int = 3):
    n = normalise(name); out = set()
    k = shard_key(n)
    if k: out.add(k)
    for w in n.split(' ')[1:max_words]:
        k = shard_key(w)
        if k: out.add(k)
    return out

class Writer:
    def __init__(self): self.shards = {}; self.seen = set(); self.count = 0
    def add(self, name: str, kind: str, lat: float, lng: float, alt: str = ''):
        name = name.strip()
        if len(name) < 2: return
        sig = (normalise(name), kind, round(lat, 3), round(lng, 3))
        if sig in self.seen: return
        self.seen.add(sig); self.count += 1
        rec = [name, kind, round(lat, 5), round(lng, 5)] + ([alt] if alt and alt != name else [])
        ks = keys_for(name) | (keys_for(alt) if alt else set())
        for k in ks: self.shards.setdefault(k, []).append(rec)
    def write(self, out: Path, source: str, licence: str, built: str):
        out.mkdir(parents=True, exist_ok=True); total = 0; sizes = {}
        for k, recs in self.shards.items():
            data = gzip.compress(json.dumps(recs, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), 9, mtime=0)
            (out / f'{k}.json.gz').write_bytes(data); total += len(data); sizes[k] = len(recs)
        (out / 'index.json').write_text(json.dumps({'version': 1, 'built': built, 'count': self.count, 'shards': sizes, 'source': source, 'licence': licence}, ensure_ascii=False))
        return total, len(sizes)
