"""OPTIONAL: add street-level OpenStreetMap layers to the local offline basemap.

The repository ships only Natural Earth + BBMP wards (no streets), because no OSM extract could be downloaded where it was built. To get streets,
buildings, parks, lakes, neighbourhood names and landmarks offline, download ONE extract yourself and run this script:

  Extract (ODbL, (c) OpenStreetMap contributors):
    BBBike Bangalore: https://download.bbbike.org/osm/bbbike/Bangalore/  (choose "Bangalore.osm.pbf")      ~ tens of MB
    or Geofabrik:     https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf               ~ hundreds of MB, use --bbox
  Windows (PowerShell, from rescuenet-x2\\frontend):
    pip install osmium shapely
    python scripts\\build_osm_layers.py --pbf C:\\data\\Bangalore.osm.pbf --out public\\basemap
  Then reload the app: the map picks up public\\basemap\\osm_*.json automatically and shows streets, water, parks, buildings, places and landmarks offline.
Output is clipped to the Bengaluru window, simplified and rounded; buildings are written only if --buildings is given (large). Attribution is added to manifest.json.
"""
import argparse, datetime, json
from pathlib import Path
import osmium
from shapely.geometry import box, mapping
from shapely import wkb

ROAD = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential', 'motorway_link', 'trunk_link', 'primary_link', 'secondary_link'}
PARK = {'park', 'garden', 'nature_reserve', 'recreation_ground'}
PLACES = {'suburb', 'neighbourhood', 'quarter', 'town', 'village', 'city', 'locality'}

class H(osmium.SimpleHandler):
    def __init__(self, win, buildings):
        super().__init__(); self.win, self.buildings = win, buildings; self.f = {k: [] for k in ('roads', 'water', 'parks', 'places', 'buildings', 'landmarks')}; self.fab = osmium.geom.WKBFactory()
    def _add(self, kind, geom, props, tol):
        if geom.is_empty or not geom.intersects(self.win): return
        g = geom.intersection(self.win).simplify(tol, preserve_topology=True)
        if not g.is_empty: self.f[kind].append({'type': 'Feature', 'properties': props, 'geometry': mapping(g)})
    def node(self, n):
        t = n.tags
        if not n.location.valid(): return
        from shapely.geometry import Point
        p = Point(n.location.lon, n.location.lat)
        if t.get('place') in PLACES and t.get('name'): self._add('places', p, {'name': t['name'], 'place': t['place']}, 0)
        elif t.get('name') and (t.get('tourism') in {'attraction', 'museum'} or t.get('historic') or t.get('amenity') in {'hospital', 'police', 'fire_station', 'place_of_worship'} or t.get('aeroway') == 'terminal'):
            self._add('landmarks', p, {'name': t['name']}, 0)
    def way(self, w):
        t = w.tags
        if t.get('highway') in ROAD:
            try: g = wkb.loads(self.fab.create_linestring(w), hex=True)
            except Exception: return
            self._add('roads', g, {'highway': t['highway'], 'name': t.get('name', '')}, 0.00004)
        elif t.get('waterway') in {'river', 'stream', 'canal'}:
            try: g = wkb.loads(self.fab.create_linestring(w), hex=True)
            except Exception: return
            self._add('water', g, {'name': t.get('name', '')}, 0.00005)
    def area(self, a):
        t = a.tags
        try: g = wkb.loads(self.fab.create_multipolygon(a), hex=True)
        except Exception: return
        if t.get('natural') == 'water' or t.get('landuse') == 'reservoir' or t.get('water'): self._add('water', g, {'name': t.get('name', '')}, 0.00005)
        elif t.get('leisure') in PARK or t.get('landuse') in {'forest', 'grass'}: self._add('parks', g, {'name': t.get('name', '')}, 0.00005)
        elif self.buildings and t.get('building'): self._add('buildings', g, {}, 0.00003)

def rnd(o, n=5):
    if isinstance(o, float): return round(o, n)
    if isinstance(o, (list, tuple)): return [rnd(x, n) for x in o]
    if isinstance(o, dict): return {k: rnd(v, n) for k, v in o.items()}
    return o

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pbf', required=True); ap.add_argument('--out', required=True); ap.add_argument('--bbox', default='77.35,12.75,77.85,13.25', help='west,south,east,north'); ap.add_argument('--buildings', action='store_true')
    a = ap.parse_args(); w, s, e, n = map(float, a.bbox.split(',')); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    h = H(box(w, s, e, n), a.buildings); h.apply_file(a.pbf, locations=True)
    names = {'roads': 'osm_roads', 'water': 'osm_water', 'parks': 'osm_parks', 'places': 'osm_places', 'buildings': 'osm_buildings', 'landmarks': 'osm_landmarks'}; counts = {}
    for k, fn in names.items():
        if not h.f[k]: continue
        (out / f'{fn}.json').write_text(json.dumps({'type': 'FeatureCollection', 'features': rnd(h.f[k])}, separators=(',', ':'), ensure_ascii=False)); counts[fn] = len(h.f[k])
    mf = out / 'manifest.json'; m = json.loads(mf.read_text()) if mf.exists() else {}
    m['osm_layers_present'] = bool(counts); m['osm'] = {'built': datetime.date.today().isoformat(), 'source_file': Path(a.pbf).name, 'bbox': [w, s, e, n], 'features': counts, 'licence': 'ODbL 1.0, (c) OpenStreetMap contributors'}
    mf.write_text(json.dumps(m, indent=1)); print(counts)

if __name__ == '__main__':
    main()
