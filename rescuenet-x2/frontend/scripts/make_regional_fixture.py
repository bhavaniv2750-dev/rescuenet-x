"""TEST FIXTURE ONLY. Builds a small PMTiles archive in the Protomaps basemap schema from the *already bundled* Natural Earth + BBMP ward
GeoJSON (public/basemap). It exists so the regional-archive code path (PMTiles + vector tile rendering + fallback + theming) can be tested
where no OpenStreetMap extract is available. It contains NO OpenStreetMap data, no streets and no buildings; it is not the South India archive,
and its metadata says so. The real archive is produced from the Geofabrik PBF by docs/frontend/REGIONAL_GIS.md.

  pip install pmtiles mapbox-vector-tile mercantile shapely
  python scripts/make_regional_fixture.py --out regional-data/fixture-bengaluru.pmtiles
"""
import argparse, gzip, json, math
from pathlib import Path
import mercantile
from mapbox_vector_tile import encode
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import write
from shapely.geometry import shape, box
from shapely import transform as _tf

SRC = Path(__file__).resolve().parent.parent / 'public' / 'basemap'
WIN = (74.0, 11.5, 78.8, 18.6)          # Karnataka window of the bundled data
BLR = (77.40, 12.80, 77.85, 13.20)


def load(name):
    return json.loads((SRC / f'{name}.json').read_text())['features']


def merc(g):
    import numpy as np
    return _tf(g, lambda c: np.array([mercantile.xy(x, y) for x, y in c]))


def build_layers():
    L = {k: [] for k in ('earth', 'landcover', 'water', 'roads', 'boundaries', 'places')}
    for f in load('states'): L['earth'].append((shape(f['geometry']), {}, 0, 15))
    for f in load('urban'): L['landcover'].append((shape(f['geometry']), {'kind': 'urban_area'}, 0, 15))
    for f in load('lakes'): L['water'].append((shape(f['geometry']), {'kind': 'lake', 'name': f['properties'].get('name', '')}, 0, 15))
    for f in load('rivers'): L['water'].append((shape(f['geometry']), {'kind': 'river'}, 4, 15))
    for f in load('roads'): L['roads'].append((shape(f['geometry']), {'kind': 'highway', 'kind_detail': 'motorway'}, 4, 15))
    for f in load('rail'): L['roads'].append((shape(f['geometry']), {'kind': 'rail', 'kind_detail': 'rail'}, 7, 15))
    for f in load('states'): L['boundaries'].append((shape(f['geometry']).boundary, {'kind': 'region', 'kind_detail': 4}, 0, 15))
    for f in load('places'):
        pop = f['properties'].get('pop_max') or 0
        L['places'].append((shape(f['geometry']), {'kind': 'locality', 'kind_detail': 'city' if pop > 1_000_000 else 'town', 'name': f['properties']['name'], 'min_zoom': 5 if pop > 1_000_000 else 8, 'population_rank': 10 if pop > 1_000_000 else 7}, 3, 15))
    for f in load('wards'):
        g = shape(f['geometry'])
        L['boundaries'].append((g.boundary, {'kind': 'locality', 'kind_detail': 9}, 11, 15))
        c = g.representative_point(); L['places'].append((c, {'kind': 'locality', 'kind_detail': 'neighbourhood', 'name': f['properties']['name'], 'min_zoom': 12, 'population_rank': 3}, 11, 15))
    return L


def tiles_for(z):
    bb = WIN if z <= 10 else BLR
    return list(mercantile.tiles(bb[0], bb[1], bb[2], bb[3], z))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--maxzoom', type=int, default=13); ap.add_argument('--search-out', default=None, help='also write a fixture search index (ward and town names)'); a = ap.parse_args()
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    L = {k: [(merc(g), p, lo, hi) for g, p, lo, hi in v] for k, v in build_layers().items()}
    items = []
    for z in range(0, a.maxzoom + 1):
        for t in ([mercantile.Tile(0, 0, 0)] if z == 0 else tiles_for(z)):
            items.append((zxy_to_tileid(t.z, t.x, t.y), t))
    items.sort(key=lambda x: x[0]); n = 0
    with write(str(out)) as w:
        for tid, t in items:
            b = mercantile.xy_bounds(t); pad = (b.right - b.left) * 0.04; clip = box(b.left - pad, b.bottom - pad, b.right + pad, b.top + pad); layers = []
            for name, feats in L.items():
                fs = []
                for g, p, lo, hi in feats:
                    if t.z < lo or t.z > hi or not g.intersects(clip): continue
                    gg = g.intersection(clip)
                    if t.z < 9: gg = gg.simplify((b.right - b.left) / 4096 * 1.5)
                    if not gg.is_empty: fs.append({'geometry': gg.wkb, 'properties': p})
                if fs: layers.append({'name': name, 'features': fs})
            if not layers: continue
            data = encode(layers, default_options={'quantize_bounds': (b.left, b.bottom, b.right, b.top), 'extents': 4096})
            w.write_tile(tid, gzip.compress(data)); n += 1
        def e7(v): return int(v * 1e7)
        w.finalize({'tile_type': TileType.MVT, 'tile_compression': Compression.GZIP, 'min_zoom': 0, 'max_zoom': a.maxzoom, 'min_lon_e7': e7(WIN[0]), 'min_lat_e7': e7(WIN[1]), 'max_lon_e7': e7(WIN[2]), 'max_lat_e7': e7(WIN[3]),
                    'center_zoom': 10, 'center_lon_e7': e7(77.59), 'center_lat_e7': e7(12.97)},
                   {'name': 'RescueNet X test fixture (NOT South India, NO OpenStreetMap data)', 'type': 'fixture', 'attribution': 'Test fixture from Natural Earth (public domain) and BBMP wards via DataMeet (CC BY-SA 2.5 India)',
                    'description': 'Synthetic-schema fixture for code-path testing only', 'vector_layers': [{'id': k, 'fields': {}} for k in L]})
    if a.search_out:
        import sys; sys.path.insert(0, str(Path(__file__).resolve().parent)); from search_index_lib import Writer
        sw = Writer()
        for f in load('wards'):
            c = shape(f['geometry']).representative_point(); sw.add(f['properties']['name'], 's', c.y, c.x)
        for f in load('places'): sw.add(f['properties']['name'], 't', f['geometry']['coordinates'][1], f['geometry']['coordinates'][0])
        sw.write(Path(a.search_out), 'fixture (BBMP wards + Natural Earth towns)', 'CC BY-SA 2.5 India / public domain', '2026-11-25')
    print(f'wrote {out} ({out.stat().st_size / 1024:.0f} KB, {n} tiles)')


if __name__ == '__main__':
    main()
