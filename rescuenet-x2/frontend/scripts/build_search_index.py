"""Builds the compact offline place-search index for the regional archive from the same OSM extract (streaming, low memory).
Only named places/landmarks are kept (cities, towns, suburbs, villages, hospitals, schools, colleges, airports, railway/metro stations, named lakes/reservoirs,
parks/forests, notable landmarks); roads and buildings are not indexed (they are in the map tiles, not in search).

  pip install osmium            # in an isolated virtual environment (see docs/frontend/REGIONAL_GIS.md)
  python scripts/build_search_index.py --pbf <southern-zone.osm.pbf> --out regional-data/search --tmp <scratch dir>

Ways (hospital/school buildings drawn as areas) need node locations; they are kept in a DISK-backed index inside --tmp (not in RAM) and --tmp is
deleted afterwards. Use --nodes-only to skip ways (much less temporary disk, fewer results). Relations (multipolygons) are not indexed.
Output is the sharded gzip layout described in search_index_lib.py. Licence of the content: ODbL 1.0, (c) OpenStreetMap contributors."""
import argparse, datetime, shutil, sys
from pathlib import Path
import osmium
sys.path.insert(0, str(Path(__file__).resolve().parent))
from search_index_lib import Writer

PLACES = {'city': 'c', 'town': 't', 'village': 'v', 'suburb': 's', 'neighbourhood': 's', 'quarter': 's', 'locality': 'o'}
AMEN = {'hospital': 'h', 'clinic': 'h', 'school': 'e', 'college': 'u', 'university': 'u', 'police': 'p', 'fire_station': 'f', 'bus_station': 'b'}

def classify(t):
    if t.get('place') in PLACES: return PLACES[t['place']]
    a = t.get('amenity')
    if a in AMEN: return AMEN[a]
    if t.get('aeroway') in ('aerodrome', 'terminal'): return 'a'
    if t.get('railway') in ('station', 'halt') or t.get('station') in ('subway', 'light_rail'): return 'r'
    if t.get('natural') == 'water' or t.get('landuse') == 'reservoir' or t.get('water') in ('lake', 'reservoir', 'pond'): return 'w'
    if t.get('leisure') in ('park', 'garden', 'nature_reserve') or t.get('boundary') in ('national_park', 'protected_area'): return 'k'
    if t.get('tourism') in ('attraction', 'museum', 'viewpoint') or t.get('historic') in ('monument', 'memorial', 'fort', 'castle', 'archaeological_site'): return 'l'
    if t.get('amenity') == 'place_of_worship' and (t.get('wikidata') or t.get('wikipedia')): return 'l'
    return None

class H(osmium.SimpleHandler):
    def __init__(self, w, ways):
        super().__init__(); self.w, self.ways = w, ways
    def _add(self, t, lat, lng):
        k = classify(t); nm = t.get('name:en') or t.get('name')
        if k and nm: self.w.add(nm, k, lat, lng, t.get('name') if t.get('name') != nm else '')
    def node(self, n):
        if n.tags and n.location.valid(): self._add(n.tags, n.location.lat, n.location.lon)
    def way(self, w):
        if not self.ways or not w.tags or not (w.tags.get('name') or w.tags.get('name:en')): return
        if classify(w.tags) is None: return
        pts = [(n.location.lat, n.location.lon) for n in w.nodes if n.location.valid()]
        if pts: self._add(w.tags, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pbf', required=True); ap.add_argument('--out', required=True); ap.add_argument('--tmp', default=None); ap.add_argument('--nodes-only', action='store_true')
    a = ap.parse_args(); w = Writer(); h = H(w, not a.nodes_only)
    tmp = Path(a.tmp or (Path(a.out).parent / '_search_tmp')); tmp.mkdir(parents=True, exist_ok=True)
    try:
        if a.nodes_only: h.apply_file(a.pbf)
        else: h.apply_file(a.pbf, locations=True, idx=f'sparse_file_array,{tmp / "nodes.idx"}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    total, shards = w.write(Path(a.out), Path(a.pbf).name, 'ODbL 1.0, (c) OpenStreetMap contributors', datetime.date.today().isoformat())
    print(f'{w.count} places, {shards} shards, {total / 1e6:.2f} MB gzipped')

if __name__ == '__main__':
    main()
