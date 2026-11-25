"""Build the local (offline) geographical basemap used when no online tile server is reachable.

Inputs (all public, redistributable; see docs/frontend/LOCAL_BASEMAP.md for licences):
  * Natural Earth 10m vector themes (public domain): roads, railroads, rivers, lakes, populated places, airports, urban areas, states.
  * BBMP ward boundaries, 243 wards, delimitation 2022 (datameet/Municipal_Spatial_Data, CC BY-SA 2.5 India).
Optional street-level OpenStreetMap layers (roads/water/parks/places/buildings) are produced by build_osm_layers.py from a Geofabrik or BBBike extract.

    python scripts/build_local_basemap.py --ne <dir with the Natural Earth zips> --wards <BBMP.geojson> --out public/basemap
Geometry is clipped to the Karnataka/Bengaluru window, simplified and coordinate-rounded so the whole set stays small. Nothing is invented: every
feature comes from the sources above, only clipped and simplified.
"""
import argparse, datetime, json, zipfile
from pathlib import Path
import shapefile                      # pyshp
from shapely.geometry import box, mapping, shape

WINDOW = box(74.0, 11.5, 78.8, 18.6)            # Karnataka and surroundings
CITY = box(77.3, 12.7, 77.95, 13.3)             # Bengaluru
KEEP_STATES = {'Karnataka', 'Tamil Nadu', 'Andhra Pradesh', 'Kerala', 'Goa', 'Maharashtra', 'Telangana'}

def read_zip(zpath: Path, work: Path):
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(work)
    shp = next(work.glob('*.shp'))
    return shapefile.Reader(str(shp), encoding='utf-8', encodingErrors='replace')

def feats(reader, window, props, tol, minlen=0):
    out = []
    fields = [f[0] for f in reader.fields[1:]]
    for sr in reader.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        g = shape(sr.shape.__geo_interface__)
        if g.is_empty or not g.intersects(window):
            continue
        g = g.intersection(window)
        if g.is_empty:
            continue
        if tol:
            g = g.simplify(tol, preserve_topology=True)
        if g.is_empty:
            continue
        out.append({'type': 'Feature', 'properties': {k: rec.get(k) for k in props}, 'geometry': mapping(g)})
    return out

def rnd(o, n=4):
    if isinstance(o, float): return round(o, n)
    if isinstance(o, (list, tuple)): return [rnd(x, n) for x in o]
    if isinstance(o, dict): return {k: rnd(v, n) for k, v in o.items()}
    return o

def write(path: Path, features):
    path.write_text(json.dumps({'type': 'FeatureCollection', 'features': rnd(features)}, separators=(',', ':'), ensure_ascii=False))
    return len(features), path.stat().st_size

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--ne', required=True); ap.add_argument('--wards', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args(); ne, out = Path(a.ne), Path(a.out); out.mkdir(parents=True, exist_ok=True); tmp = out.parent / '.basemap_tmp'
    stats = {}
    stats['roads'] = write(out / 'roads.json', feats(read_zip(ne / 'ne_10m_roads.zip', tmp / 'roads'), WINDOW, ['type', 'name', 'scalerank', 'level'], 0.004))
    stats['rail'] = write(out / 'rail.json', feats(read_zip(ne / 'ne_10m_railroads.zip', tmp / 'rail'), WINDOW, ['scalerank'], 0.004))
    stats['rivers'] = write(out / 'rivers.json', feats(read_zip(ne / 'ne_10m_rivers_lake_centerlines.zip', tmp / 'rivers'), WINDOW, ['name', 'scalerank'], 0.004))
    stats['lakes'] = write(out / 'lakes.json', feats(read_zip(ne / 'ne_10m_lakes.zip', tmp / 'lakes'), WINDOW, ['name'], 0.004))
    stats['places'] = write(out / 'places.json', feats(read_zip(ne / 'ne_10m_populated_places_simple.zip', tmp / 'places'), WINDOW, ['name', 'pop_max', 'featurecla', 'adm1name'], 0))
    stats['airports'] = write(out / 'airports.json', feats(read_zip(ne / 'ne_10m_airports.zip', tmp / 'air'), WINDOW, ['name', 'iata_code', 'type'], 0))
    stats['urban'] = write(out / 'urban.json', feats(read_zip(ne / 'ne_10m_urban_areas.zip', tmp / 'urban'), WINDOW, ['featurecla'], 0.003))
    st = [f for f in feats(read_zip(ne / 'ne_10m_admin_1_states_provinces.zip', tmp / 'states'), WINDOW, ['name', 'admin'], 0.004) if f['properties']['admin'] == 'India' and f['properties']['name'] in KEEP_STATES]
    stats['states'] = write(out / 'states.json', st)
    w = json.loads(Path(a.wards).read_text()); wf = []
    for f in w['features']:
        g = shape(f['geometry']).simplify(0.0002, preserve_topology=True)
        if g.is_empty: continue
        p = f['properties']; wf.append({'type': 'Feature', 'properties': {'no': p.get('KGISWardNo'), 'name': p.get('KGISWardName')}, 'geometry': mapping(g)})
    stats['wards'] = write(out / 'wards.json', wf)
    bs = [shape(f['geometry']).bounds for f in wf]; b = (min(x[0] for x in bs), min(x[1] for x in bs), max(x[2] for x in bs), max(x[3] for x in bs))
    manifest = {'built': datetime.date.today().isoformat(), 'window_karnataka': list(WINDOW.bounds), 'bengaluru_ward_extent': [round(x, 4) for x in b], 'files': {k: {'features': v[0], 'bytes': v[1]} for k, v in stats.items()},
                'sources': [
                    {'name': 'Natural Earth 10m (roads, railroads, rivers and lake centerlines, lakes, populated places, airports, urban areas, admin-1)', 'url': 'https://www.naturalearthdata.com/', 'licence': 'Public domain', 'note': 'small-scale data: major roads only, no residential streets'},
                    {'name': 'BBMP wards 2022 (243 wards), scraped from KSRSAC KGIS by DataMeet', 'url': 'https://github.com/datameet/Municipal_Spatial_Data/tree/master/Bangalore', 'licence': 'CC BY-SA 2.5 India', 'note': 'ward names are the neighbourhood names shown'}],
                'osm_layers_present': False}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest['files'], indent=1)); print('total bytes', sum(v[1] for v in stats.values()))

if __name__ == '__main__':
    main()
