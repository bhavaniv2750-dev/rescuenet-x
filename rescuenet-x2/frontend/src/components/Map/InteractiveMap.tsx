import { useTheme } from '../../lib/theme';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { MarkerClusterGroup } from 'leaflet.markercluster';
import { BASEMAPS, BASEMAP_KEY, STYLE_KEY } from './basemaps';
import type { BasemapId } from './basemaps';
import { clusterIcon, esc, popup, sevColor } from './markers';
import { LOCAL_ATTRIBUTION, drawLocal, loadLocalBasemap, paletteFor, searchLocal } from './localBasemap';
import type { LocalData, LocalHandle, LocalHit, Theme } from './localBasemap';
import { drawRegional, inBounds, probeRegional } from './regional';
import type { RegionalHandle, RegionalInfo } from './regional';
import { searchRegional } from './regionalSearch';
import { PRESETS, PRESET_ORDER } from './presets';
import type { PresetId } from './presets';
import { kindOfFacility, legendSvg, presetIcon } from './styleMarkers';
import type { MarkerKind } from './styleMarkers';
import type { Alert, Facility, Incident, RescueTeam, RiverGauge } from '../../api/types';

interface InteractiveMapProps {
  incidents?: Incident[];
  teams?: RescueTeam[];
  facilities?: Facility[];
  gauges?: RiverGauge[];
  catchmentsGeoJSON?: any;
  alerts?: Alert[];
  selectedIncident?: Incident | null;
  onSelectIncident?: (incident: Incident) => void;
  onMapClick?: (coords: { lat: number; lng: number }) => void;
  height?: string;
  zoom?: number;
  center?: [number, number];
  /** Force a preset (used by the comparison screenshots); users normally choose it in the panel. */
  forcePreset?: PresetId;
}

interface Info { title: string; badge: string | null; rows: [string, unknown][]; lat: number; lng: number }
type BaseChoice = 'auto' | BasemapId | 'local' | 'regional';
type Active = BasemapId | 'local' | 'regional' | 'none';
// secondary online provider (a different, permitted provider) tried when the first one cannot be reached
const SECONDARY: Record<BasemapId, BasemapId> = { dark: 'standard', light: 'standard', voyager: 'standard', standard: 'voyager' };
const BENGALURU: [number, number] = [12.9716, 77.5946];

export const InteractiveMap: React.FC<InteractiveMapProps> = ({
  incidents = [], teams = [], facilities = [], gauges = [], catchmentsGeoJSON, alerts = [], selectedIncident, onSelectIncident, onMapClick,
  height = '500px', zoom = 11, center = BENGALURU, forcePreset,
}) => {
  const shellRef = useRef<HTMLDivElement>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const baseRef = useRef<L.TileLayer | null>(null);
  const catchRef = useRef<L.GeoJSON | null>(null);
  const incRef = useRef<L.LayerGroup | null>(null);
  const teamRef = useRef<L.LayerGroup | null>(null);
  const facRef = useRef<L.LayerGroup | null>(null);
  const gaugeRef = useRef<L.LayerGroup | null>(null);
  const alertRef = useRef<L.LayerGroup | null>(null);
  const extraRef = useRef<L.LayerGroup | null>(null);       // the user's own location and a searched place (never data)
  const onMapClickRef = useRef(onMapClick);
  useEffect(() => { onMapClickRef.current = onMapClick; }, [onMapClick]);

  const [on, setOn] = useState({ catch: true, inc: true, team: true, fac: true, gauge: true, alert: true });
  const [preset, setPreset] = useState<PresetId>(forcePreset ?? 'classic');
  const [baseChoice, setBaseChoice] = useState<BaseChoice>('auto');
  const [step, setStep] = useState(0);
  const localRef = useRef<LocalHandle | null>(null);
  const regionalRef = useRef<RegionalHandle | null>(null);
  const [regional, setRegional] = useState<RegionalInfo | null>(null);   // null: no regional archive is configured or reachable
  const [outside, setOutside] = useState(false);
  useEffect(() => { let dead = false; probeRegional().then((i) => { if (!dead) setRegional(i); }); return () => { dead = true; }; }, []);
  const localDataRef = useRef<LocalData | null>(null);
  const { mapResolved, map: mapPref, setMapAppearance } = useTheme();   // independent of the application theme
  const [tileError, setTileError] = useState(false);
  const [mapLoading, setMapLoading] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const [layersOpen, setLayersOpen] = useState<boolean>(() => typeof window === 'undefined' || window.innerWidth > 760);
  const [selId, setSelId] = useState<string | null>(null);
  const [info, setInfo] = useState<Info | null>(null);
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<(LocalHit & { online?: boolean })[] | null>(null);
  const [hitsLabel, setHitsLabel] = useState('');
  const [searchMsg, setSearchMsg] = useState<string | null>(null);
  const [locMsg, setLocMsg] = useState<string | null>(null);
  const P = PRESETS[preset];
  const autoBase: BasemapId = mapResolved === 'dark' ? 'dark' : (preset === 'navigation' || preset === 'flood') ? 'voyager' : 'light';
  const basemap: BasemapId = baseChoice === 'auto' || baseChoice === 'local' || baseChoice === 'regional' ? autoBase : baseChoice;
  // availability order: chosen online map -> secondary online map -> local offline map -> unavailable
  const chain: Active[] = baseChoice === 'local' ? ['local', 'none']
    : baseChoice === 'regional' ? [...(regional ? ['regional' as const] : []), 'local', 'none']
    : [basemap, SECONDARY[basemap], ...(regional ? ['regional' as const] : []), 'local', 'none'];
  const chainKey = chain.join('>');
  const active: Active = chain[Math.min(step, chain.length - 1)];
  const theme: Theme = basemap === 'dark' ? 'dark' : 'light';
  const cardMode = P.cards;

  // restore remembered choices (this browser only)
  useEffect(() => {
    try {
      const sp = localStorage.getItem(STYLE_KEY) as PresetId | null; if (!forcePreset && sp && PRESETS[sp]) setPreset(sp);
      const sb = localStorage.getItem(BASEMAP_KEY) as BaseChoice | null; if (sb && (sb === 'local' || sb === 'regional' || BASEMAPS[sb as BasemapId])) setBaseChoice(sb);
    } catch { /* optional */ }
  }, [forcePreset]);
  const choosePreset = (id: PresetId) => { setPreset(id); setInfo(null); try { localStorage.setItem(STYLE_KEY, id); } catch { /* optional */ } };
  const chooseBase = (id: BaseChoice) => { setBaseChoice(id); try { id === 'auto' ? localStorage.removeItem(BASEMAP_KEY) : localStorage.setItem(BASEMAP_KEY, id); } catch { /* optional */ } };

  // ---- map creation
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;
    const map = L.map(mapContainerRef.current, { center, zoom, zoomControl: false, attributionControl: true, maxZoom: 19, minZoom: 3, zoomSnap: 0.5 });
    map.attributionControl.setPrefix(false);
    map.on('click', (e: L.LeafletMouseEvent) => { onMapClickRef.current?.({ lat: e.latlng.lat, lng: e.latlng.lng }); });
    const scale = () => { const z = map.getZoom(); shellRef.current?.style.setProperty('--pin-scale', String(Math.max(0.62, Math.min(1.12, 0.62 + (z - 9) * 0.085)))); };
    map.on('zoomend', scale); scale();
    const cluster = (): L.LayerGroup => { const g = new MarkerClusterGroup({ maxClusterRadius: 44, showCoverageOnHover: false, spiderfyOnMaxZoom: true, iconCreateFunction: clusterIcon }); map.addLayer(g as unknown as L.Layer); return g as unknown as L.LayerGroup; };
    incRef.current = cluster(); facRef.current = cluster(); gaugeRef.current = cluster();
    teamRef.current = L.layerGroup().addTo(map); alertRef.current = L.layerGroup().addTo(map); extraRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; baseRef.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- basemap with automatic fallback (online -> secondary online -> local offline -> unavailable)
  useEffect(() => { setStep(0); }, [chainKey]);
  useEffect(() => {
    const map = mapRef.current; if (!map) return;
    const clearLocal = () => { localRef.current?.remove(); localRef.current = null; map.attributionControl.removeAttribution(LOCAL_ATTRIBUTION); };
    const clearRegional = () => { if (regionalRef.current) { regionalRef.current.remove(); regionalRef.current = null; if (regional) map.attributionControl.removeAttribution(regional.attribution); } };
    clearRegional();
    if (baseRef.current) { map.removeLayer(baseRef.current); baseRef.current = null; }
    clearLocal(); setTileError(false);
    if (active === 'none') { setMapLoading(false); setTileError(true); return; }
    if (active === 'regional' && regional) {
      let dead = false; setMapLoading(true);
      drawRegional(map, regional, theme, preset, () => { if (!dead) setStep((n) => n + 1); }).then((h) => {
        if (dead) { h.remove(); return; } regionalRef.current = h; map.attributionControl.addAttribution(regional.attribution); setMapLoading(false);
      }).catch(() => { if (!dead) setStep((n) => n + 1); });
      return () => { dead = true; clearRegional(); };
    }
    if (active === 'local') {
      let dead = false; setMapLoading(true);
      loadLocalBasemap().then((d) => {
        if (dead) return; localDataRef.current = d; localRef.current = drawLocal(map, d, theme, preset); map.attributionControl.addAttribution(LOCAL_ATTRIBUTION); setMapLoading(false);
      }).catch(() => { if (!dead) setStep((n) => n + 1); });
      return () => { dead = true; clearLocal(); };
    }
    if (active === 'regional') { setStep((n) => n + 1); return; }   // archive not available: continue down the chain
    const def = BASEMAPS[active]; setMapLoading(true);
    const layer = L.tileLayer(def.url, { attribution: def.attribution, subdomains: def.subdomains ?? 'abc', maxZoom: def.maxZoom });
    let errors = 0, loaded = false, advanced = false;
    const next = () => { if (!advanced && !loaded) { advanced = true; setStep((n) => n + 1); } };
    layer.on('tileerror', () => { errors += 1; if (errors >= 3) next(); });
    layer.on('tileload', () => { loaded = true; errors = 0; setMapLoading(false); });
    layer.addTo(map); layer.bringToBack(); baseRef.current = layer;
    const t = window.setTimeout(next, 6000);          // nothing arrived at all: treat the provider as unreachable
    return () => window.clearTimeout(t);
  }, [active, theme, preset, regional]); // eslint-disable-line react-hooks/exhaustive-deps

  // tell the user when the view leaves the area the regional archive covers (it never invents data outside it)
  useEffect(() => {
    const map = mapRef.current; if (!map || active !== 'regional' || !regional) { setOutside(false); return; }
    const check = () => { const c = map.getCenter(); setOutside(!inBounds(regional.bounds, c.lat, c.lng)); };
    check(); map.on('moveend', check); return () => { map.off('moveend', check); };
  }, [active, regional]);

  // ---- helpers
  const pick = useCallback((m: L.Marker, i: Info, id: string | null, open: () => void) => {
    m.on('click', () => { if (id) setSelId(id); if (cardMode) setInfo(i); else open(); });
  }, [cardMode]);
  const bind = (m: L.Marker, i: Info) => { if (!cardMode) m.bindPopup(popup(i.title, i.badge, i.rows)); };

  // ---- data layers (same records for every preset)
  useEffect(() => {
    const map = mapRef.current; if (!map) return;
    if (catchRef.current) { map.removeLayer(catchRef.current); catchRef.current = null; }
    if (catchmentsGeoJSON && on.catch) {
      const fill = preset === 'flood' ? 0.07 : preset === 'navigation' ? 0.05 : 0.1;
      const layer = L.geoJSON(catchmentsGeoJSON, {
        style: () => ({ color: preset === 'navigation' ? '#2a7fb8' : '#22b8cf', weight: preset === 'flood' ? 1.3 : 1.5, opacity: 0.85, fillColor: preset === 'navigation' ? '#2a7fb8' : '#22b8cf', fillOpacity: fill }),
        onEachFeature: (f, l) => { l.bindPopup(popup(String(f.properties.catchment_name ?? 'Catchment'), 'CATCHMENT', [['Gauge ID', f.properties.gauge_id], ['Source', 'IndoFloods shapefiles (historical boundary, not a flooded area)'], ['Boundary vertices', f.properties.points_count]])); },
      });
      layer.addTo(map); layer.bringToBack(); catchRef.current = layer;
    }
  }, [catchmentsGeoJSON, on.catch, preset]);

  useEffect(() => {
    const layer = incRef.current; if (!layer) return; layer.clearLayers(); if (!on.inc) return;
    incidents.forEach((inc) => {
      if (!inc.latitude || !inc.longitude) return;
      const sel = selId === inc.id || selectedIncident?.id === inc.id;
      const m = L.marker([inc.latitude, inc.longitude], { icon: presetIcon(preset, 'incident', { severity: inc.severity, selected: sel }), title: `${inc.severity} incident: ${inc.title}`, zIndexOffset: sel ? 900 : (inc.severity || '').toUpperCase() === 'CRITICAL' ? 400 : 0 });
      const i: Info = { title: inc.title, badge: inc.severity, lat: inc.latitude, lng: inc.longitude, rows: [['ID', inc.id], ['Area', inc.area], ['People affected', inc.people_affected], ['Status', String(inc.status).replace(/_/g, ' ')], ['Source', inc.source], ['Data', inc.data_label]] };
      bind(m, i);
      if (P.labels && (sel || (inc.severity || '').toUpperCase() === 'CRITICAL')) m.bindTooltip(esc(inc.title.length > 30 ? inc.title.slice(0, 29) + '…' : inc.title), { permanent: true, direction: 'right', className: 'rn-label', offset: [8, 0] });
      pick(m, i, inc.id, () => m.openPopup());
      m.on('click', () => { onSelectIncident?.(inc); });
      m.addTo(layer);
    });
  }, [incidents, on.inc, preset, selId, selectedIncident, onSelectIncident, cardMode]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const layer = teamRef.current; if (!layer) return; layer.clearLayers(); if (!on.team) return;
    teams.forEach((t) => {
      if (!t.latitude || !t.longitude) return;
      const m = L.marker([t.latitude, t.longitude], { icon: presetIcon(preset, 'team', { available: t.status === 'AVAILABLE' }), title: `Rescue squad ${t.callsign}, ${t.status}` });
      const i: Info = { title: `${t.name} (${t.callsign})`, badge: t.status, lat: t.latitude, lng: t.longitude, rows: [['Vehicle', t.vehicle_type], ['Members', t.members_count], ['Base', t.base_station], ['Contact', t.contact_number]] };
      bind(m, i); pick(m, i, null, () => m.openPopup()); m.addTo(layer);
    });
  }, [teams, on.team, preset, cardMode]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const layer = facRef.current; if (!layer) return; layer.clearLayers(); if (!on.fac) return;
    facilities.forEach((f) => {
      if (!f.latitude || !f.longitude) return;
      const m = L.marker([f.latitude, f.longitude], { icon: presetIcon(preset, kindOfFacility(f.facility_type), { facilityType: f.facility_type }), title: `${f.facility_type.replace(/_/g, ' ').toLowerCase()}: ${f.name}` });
      const i: Info = { title: f.name, badge: f.facility_type.replace(/_/g, ' '), lat: f.latitude, lng: f.longitude, rows: [['Capacity', `${f.current_occupancy} / ${f.total_capacity}`], ['Free places', f.total_capacity - f.current_occupancy], ['Status', String(f.status).replace(/_/g, ' ')], ['Address', f.address], ['Contact', f.contact], ['Data', f.data_label]] };
      bind(m, i); pick(m, i, null, () => m.openPopup()); m.addTo(layer);
    });
  }, [facilities, on.fac, preset, cardMode]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const layer = gaugeRef.current; if (!layer) return; layer.clearLayers(); if (!on.gauge) return;
    gauges.forEach((g) => {
      if (!g.latitude || !g.longitude) return;
      const m = L.marker([g.latitude, g.longitude], { icon: presetIcon(preset, 'gauge'), title: `River gauge station: ${g.station_name}` });
      const i: Info = { title: g.station_name, badge: 'GAUGE', lat: g.latitude, lng: g.longitude, rows: [['River', g.river], ['Basin', g.basin], ['Warning threshold', `${g.warning_level_m} m`], ['Danger threshold', `${g.danger_level_m} m`], ['Gauge ID', g.gauge_id], ['Live reading', 'not available']] };
      bind(m, i); pick(m, i, null, () => m.openPopup()); m.addTo(layer);
    });
  }, [gauges, on.gauge, preset, cardMode]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const layer = alertRef.current; if (!layer) return; layer.clearLayers(); if (!on.alert) return;
    alerts.forEach((a) => {
      if (!a.latitude || !a.longitude || a.status === 'RESOLVED') return;
      const color = preset === 'flood' ? '#ffb020' : sevColor(a.severity === 'WARNING' ? 'MODERATE' : a.severity);
      const c = L.circle([a.latitude, a.longitude], { radius: a.radius_km * 1000, color, fillColor: color, fillOpacity: preset === 'flood' ? 0.12 : 0.1, weight: 1.5, dashArray: '5, 6' });
      c.bindPopup(popup(a.title, a.severity, [['Alert radius', `${a.radius_km} km`], ['Area', a.area], ['Message', a.message], ['Acknowledged by', a.acknowledged_count], ['Data', a.data_label]]));
      c.addTo(layer);
    });
  }, [alerts, on.alert, preset]);

  // ---- view control
  useEffect(() => { mapRef.current?.invalidateSize(); }, [fullscreen]);
  useEffect(() => { const f = () => setFullscreen(Boolean(document.fullscreenElement)); document.addEventListener('fullscreenchange', f); return () => document.removeEventListener('fullscreenchange', f); }, []);
  useEffect(() => { mapRef.current?.flyTo(center, zoom, { duration: 0.6 }); }, [center[0], center[1], zoom]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (selectedIncident && mapRef.current) { setSelId(selectedIncident.id); mapRef.current.flyTo([selectedIncident.latitude, selectedIncident.longitude], 14, { duration: 0.6 }); } }, [selectedIncident]);
  const toggleFullscreen = () => { const el = shellRef.current; if (!el) return; if (document.fullscreenElement) { document.exitFullscreen?.(); return; } if (el.requestFullscreen) el.requestFullscreen().catch(() => setFullscreen((v) => !v)); else setFullscreen((v) => !v); };
  const recenter = () => mapRef.current?.flyTo(BENGALURU, 11, { duration: 0.6 });
  const fitAll = () => {
    const pts: [number, number][] = [];
    if (on.inc) incidents.forEach((i) => i.latitude && pts.push([i.latitude, i.longitude]));
    if (on.team) teams.forEach((i) => i.latitude && pts.push([i.latitude, i.longitude]));
    if (on.fac) facilities.forEach((i) => i.latitude && pts.push([i.latitude, i.longitude]));
    if (on.gauge) gauges.forEach((i) => i.latitude && pts.push([i.latitude, i.longitude]));
    if (pts.length) mapRef.current?.flyToBounds(L.latLngBounds(pts), { padding: [48, 48], maxZoom: 15, duration: 0.7 }); else recenter();
  };
  const locate = () => {
    if (!navigator.geolocation) { setLocMsg('Your browser cannot share its location.'); return; }
    setLocMsg('Asking your device for its location…');
    navigator.geolocation.getCurrentPosition((pos) => {
      const map = mapRef.current, ex = extraRef.current; if (!map || !ex) return;
      ex.eachLayer((l) => { if ((l as L.Layer & { _me?: boolean })._me) ex.removeLayer(l); });
      const here: [number, number] = [pos.coords.latitude, pos.coords.longitude];
      const dot = L.marker(here, { icon: L.divIcon({ className: 'rn-m-wrap', html: '<span class="rn-me"></span>', iconSize: [18, 18], iconAnchor: [9, 9] }), title: 'Your current location', zIndexOffset: 1000 }) as L.Marker & { _me?: boolean };
      dot._me = true; dot.addTo(ex);
      const acc = L.circle(here, { radius: pos.coords.accuracy, color: '#4aa3ff', weight: 1, fillOpacity: 0.1 }) as L.Circle & { _me?: boolean }; acc._me = true; acc.addTo(ex);
      map.flyTo(here, 15, { duration: 0.7 }); setLocMsg(`Your location (accuracy about ${Math.round(pos.coords.accuracy)} m). Shown only on your screen.`);
    }, () => setLocMsg('Location was not shared.'), { enableHighAccuracy: true, timeout: 10000 });
  };
  // Place search. Local names (wards, towns, airports, any OSM places) are searched first and offline. Online geocoding (OpenStreetMap Nominatim) runs only when
  // the button is pressed and sends the typed text to that service.
  const search = async (e: React.FormEvent) => {
    e.preventDefault(); if (q.trim().length < 2) return;
    setSearchMsg('Searching…'); setHits(null);
    try {
      const c = mapRef.current?.getCenter();
      const reg = regional ? await searchRegional(q, c ? [c.lat, c.lng] : undefined).catch(() => null) : null;
      if (reg && reg.length) { setHits(reg); setHitsLabel('Regional places (offline index)'); setSearchMsg(null); return; }
      const d = await loadLocalBasemap(); const h = searchLocal(d, q); setHits(h); setHitsLabel('Local places (offline data)'); setSearchMsg(h.length ? null : regional ? 'No offline match in the regional index or the basic local data.' : 'No local match. The local data covers BBMP wards, major towns and airports only.');
    }
    catch { setSearchMsg('Local place data could not be loaded.'); }
  };
  const searchOnline = async () => {
    setSearchMsg('Searching online…');
    try {
      const r = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&countrycodes=in&viewbox=77.3,13.3,77.9,12.7&q=${encodeURIComponent(q.trim())}`, { headers: { Accept: 'application/json' } });
      if (!r.ok) throw new Error(String(r.status));
      const j = (await r.json()) as { display_name: string; lat: string; lon: string }[];
      setHits(j.map((x) => ({ name: x.display_name, kind: 'OpenStreetMap place', lat: parseFloat(x.lat), lng: parseFloat(x.lon), online: true }))); setHitsLabel('Online results (OpenStreetMap Nominatim)'); setSearchMsg(j.length ? null : 'No matching place found online.');
    } catch { setSearchMsg('Online place search is unavailable (the geocoding service could not be reached).'); }
  };
  const goHit = (h: LocalHit & { online?: boolean }) => {
    const map = mapRef.current, ex = extraRef.current; if (!map || !ex) return;
    ex.eachLayer((l) => { if ((l as L.Layer & { _s?: boolean })._s) ex.removeLayer(l); });
    const pos: [number, number] = [h.lat, h.lng];
    const m = L.marker(pos, { icon: L.divIcon({ className: 'rn-m-wrap', html: '<span class="rn-search-pin"></span>', iconSize: [20, 20], iconAnchor: [10, 10] }), title: h.name }) as L.Marker & { _s?: boolean };
    m._s = true; m.bindPopup(popup(h.name.split(',')[0], 'SEARCH RESULT', [['Place', h.name], ['Kind', h.kind], ['Source', h.online ? 'OpenStreetMap Nominatim (online)' : hitsLabel.startsWith('Regional') ? 'Regional offline index' : 'Local offline data']])).addTo(ex).openPopup();
    map.flyTo(pos, h.kind.startsWith('BBMP') ? 14 : 13, { duration: 0.7 }); setHits(null); setSearchMsg(null);
  };

  const toggles: { key: keyof typeof on; label: string; n: number }[] = [
    { key: 'catch', label: 'Catchment boundaries', n: catchmentsGeoJSON?.features?.length || 0 }, { key: 'inc', label: 'Incidents', n: incidents.length },
    { key: 'team', label: 'Rescue squads', n: teams.length }, { key: 'fac', label: 'Hospitals, shelters, camps', n: facilities.length },
    { key: 'gauge', label: 'Gauge stations', n: gauges.length }, { key: 'alert', label: 'Alert areas', n: alerts.filter((a) => a.status !== 'RESOLVED').length },
  ];
  const kinds = new Set(facilities.map((f) => f.facility_type));
  const legend: { svg: string; text: string }[] = [
    ...(['CRITICAL', 'HIGH', 'MODERATE', 'LOW'] as const).map((s) => ({ svg: legendSvg(preset, 'incident', { severity: s }), text: `${s.toLowerCase()} incident` })),
    ...(teams.length ? [{ svg: legendSvg(preset, 'team', { available: true }), text: 'rescue squad' }] : []),
    ...([...kinds].map((t) => ({ svg: legendSvg(preset, kindOfFacility(t) as MarkerKind, { facilityType: t }), text: t.replace(/_/g, ' ').toLowerCase() }))),
    ...(gauges.length ? [{ svg: legendSvg(preset, 'gauge'), text: 'river gauge station' }] : []),
  ];

  return (
    <div ref={shellRef} className={`rn-map-frame map-host map-${active === 'local' || active === 'regional' ? 'local-' + theme : basemap} style-${preset}${fullscreen ? ' map-fs' : ''}${P.search ? ' has-search' : ''}`}
      style={{ height: fullscreen ? undefined : height, ['--map-bg' as string]: active === 'local' || active === 'regional' ? paletteFor(theme, preset).land : BASEMAPS[basemap].background }} role="region" aria-label={`Interactive map, ${P.label} style`}>
      <div ref={mapContainerRef} className="map-canvas" />

      {P.search && (
        <form className="map-search" onSubmit={search} role="search" aria-label="Search for a place">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a ward, town or place" aria-label="Search for a place" maxLength={120} />
          <button type="submit" disabled={q.trim().length < 2}>Search</button>
          {(hits || searchMsg) && (
            <div className="map-search-results" role="status">
              {hits && <p className="note"><strong>{hitsLabel}</strong></p>}
              {searchMsg && <p>{searchMsg}</p>}
              {hits?.map((h) => <button type="button" key={`${h.lat}${h.lng}${h.name}`} onClick={() => goHit(h)}>{h.name} <span className="kind">{h.kind}</span></button>)}
              <button type="button" className="online" onClick={searchOnline}>Search online instead (sends your text to OpenStreetMap Nominatim)</button>
            </div>
          )}
        </form>
      )}

      <div className="map-ctl" role="group" aria-label="Map controls">
        <button type="button" onClick={() => mapRef.current?.zoomIn()} aria-label="Zoom in">+</button>
        <button type="button" onClick={() => mapRef.current?.zoomOut()} aria-label="Zoom out">−</button>
        <button type="button" onClick={fitAll} aria-label="Fit all data" title="Fit all data">⛶</button>
        <button type="button" onClick={recenter} aria-label="Recenter on Bengaluru" title="Recenter on Bengaluru">⌖</button>
        <button type="button" onClick={locate} aria-label="Show my location" title="Show my location">◉</button>
        <button type="button" onClick={toggleFullscreen} aria-label={fullscreen ? 'Exit full screen' : 'Full screen'} aria-pressed={fullscreen} title="Full screen">{fullscreen ? '⤡' : '⤢'}</button>
      </div>

      <details className="map-layers" open={layersOpen} onToggle={(e) => setLayersOpen((e.currentTarget as HTMLDetailsElement).open)}>
        <summary>Style and layers</summary>
        <div className="map-layers-body" role="group" aria-label="Map style and layers">
          <label className="map-select">Map style
            <select value={preset} onChange={(e) => choosePreset(e.target.value as PresetId)} disabled={Boolean(forcePreset)}>{PRESET_ORDER.map((id) => <option key={id} value={id}>{PRESETS[id].label}</option>)}</select>
          </label>
          <p className="map-blurb">{P.blurb}</p>
          <label className="map-select">Base map
            <select value={baseChoice} onChange={(e) => chooseBase(e.target.value as BaseChoice)}>
              <option value="auto">Automatic (online, then offline)</option>{(Object.keys(BASEMAPS) as BasemapId[]).map((id) => <option key={id} value={id}>{BASEMAPS[id].label} (online)</option>)}{regional && <option value="regional">{regional.isFixture ? 'Regional offline map (TEST FIXTURE)' : 'Regional offline map (vector archive)'}</option>}<option value="local">Local offline map (basic)</option>
            </select>
          </label>
          {baseChoice === 'auto' && <label className="map-select">Map appearance<select value={mapPref} onChange={(e) => setMapAppearance(e.target.value as 'follow' | 'light' | 'dark')}><option value="follow">Follow app theme</option><option value="light">Light</option><option value="dark">Dark</option></select></label>}
          {toggles.filter((t) => t.n > 0 || t.key === 'inc').map((t) => (
            <label key={t.key} className="map-toggle"><input type="checkbox" checked={on[t.key]} onChange={(e) => setOn({ ...on, [t.key]: e.target.checked })} /><span>{t.label}</span><span className="map-count">{t.n}</span></label>
          ))}
        </div>
      </details>

      <details className="map-legend-box">
        <summary>Legend</summary>
        <ul>
          {legend.map((l) => <li key={l.text}><span className="lg-svg" dangerouslySetInnerHTML={{ __html: l.svg }} /> {l.text}</li>)}
          <li className="lg-note">Numbered circles group nearby markers. Seeded records are simulated. Catchments are historical boundaries, not flooded areas; gauges show thresholds only.</li>
        </ul>
      </details>

      {info && cardMode && (
        <aside className="rn-info-card" aria-label="Selected item">
          <button type="button" className="rn-info-card-x" onClick={() => setInfo(null)} aria-label="Close information card">×</button>
          <div dangerouslySetInnerHTML={{ __html: popup(info.title, info.badge, info.rows) }} />
          <div className="rn-info-card-actions"><button type="button" onClick={() => mapRef.current?.flyTo([info.lat, info.lng], 16, { duration: 0.6 })}>Zoom to</button></div>
        </aside>
      )}
      <div className={`map-source ${active === 'local' || active === 'regional' ? 'is-local' : active === 'none' ? 'is-none' : 'is-online'}`} role="status">
        {active === 'regional' ? (regional?.isFixture ? 'Offline regional map: TEST FIXTURE' : 'Offline map: regional vector archive') : active === 'local' ? 'Offline map: locally stored data' : active === 'none' ? 'No base map available' : `Online map: ${BASEMAPS[active].label}`}
        {active !== 'local' && active !== 'regional' && active !== 'none' && step > 0 ? ' (fallback)' : ''}
        {active === 'regional' && outside ? ' · outside archive coverage' : ''}
      </div>
      {(locMsg || (mapLoading && !tileError)) && <div className="map-status" role="status">{locMsg ?? 'Loading map…'}</div>}
      {tileError && (
        <div className="rn-map-notice" role="status">
          No online base map is reachable and the local offline map data could not be loaded. Pins and polygons are still drawn at their true positions; only the background is missing.
        </div>
      )}
    </div>
  );
};
