import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
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
}

export const InteractiveMap: React.FC<InteractiveMapProps> = ({
  incidents = [],
  teams = [],
  facilities = [],
  gauges = [],
  catchmentsGeoJSON,
  alerts = [],
  selectedIncident,
  onSelectIncident,
  onMapClick,
  height = '500px',
  zoom = 11,
  center = [12.9716, 77.5946], // Bengaluru coordinates
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);

  // Layer groups
  const catchmentsLayerRef = useRef<L.GeoJSON | null>(null);
  const incidentsLayerRef = useRef<L.LayerGroup | null>(null);
  const teamsLayerRef = useRef<L.LayerGroup | null>(null);
  const facilitiesLayerRef = useRef<L.LayerGroup | null>(null);
  const gaugesLayerRef = useRef<L.LayerGroup | null>(null);
  const alertsLayerRef = useRef<L.LayerGroup | null>(null);

  // Layer Visibility state
  const [showCatchments, setShowCatchments] = useState(true);
  const [showIncidents, setShowIncidents] = useState(true);
  const [showTeams, setShowTeams] = useState(true);
  const [showFacilities, setShowFacilities] = useState(true);
  const [showGauges, setShowGauges] = useState(true);
  const [showAlerts, setShowAlerts] = useState(true);
  const [tileError, setTileError] = useState(false);

  // Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (mapInstanceRef.current) return; // already initialized

    const map = L.map(mapContainerRef.current, {
      center,
      zoom,
      zoomControl: false,
    });

    // 100% Free OpenStreetMap tile layer - requires ZERO paid API keys
    const osmLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
      maxZoom: 19,
    });

    osmLayer.on('tileerror', () => {
      setTileError(true);
    });
    osmLayer.on('load', () => {
      setTileError(false);
    });

    osmLayer.addTo(map);

    L.control.zoom({ position: 'topright' }).addTo(map);

    // Click handler
    map.on('click', (e: L.LeafletMouseEvent) => {
      if (onMapClick) {
        onMapClick({ lat: e.latlng.lat, lng: e.latlng.lng });
      }
    });

    // Initialize layer groups
    incidentsLayerRef.current = L.layerGroup().addTo(map);
    teamsLayerRef.current = L.layerGroup().addTo(map);
    facilitiesLayerRef.current = L.layerGroup().addTo(map);
    gaugesLayerRef.current = L.layerGroup().addTo(map);
    alertsLayerRef.current = L.layerGroup().addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Update Catchments Layer
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (catchmentsLayerRef.current) {
      map.removeLayer(catchmentsLayerRef.current);
      catchmentsLayerRef.current = null;
    }

    if (catchmentsGeoJSON && showCatchments) {
      const layer = L.geoJSON(catchmentsGeoJSON, {
        style: (feature) => ({
          color: feature?.properties?.color || '#06b6d4',
          weight: 2,
          opacity: 0.8,
          fillColor: feature?.properties?.color || '#06b6d4',
          fillOpacity: 0.15,
        }),
        onEachFeature: (feature, layer) => {
          layer.bindPopup(`
            <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
              <strong style="color: #0891b2;">${feature.properties.catchment_name}</strong><br/>
              <span style="color: #64748b;">Gauge ID:</span> ${feature.properties.gauge_id}<br/>
              <span style="color: #64748b;">Source:</span> IndoFloods Shapefiles<br/>
              <span style="color: #64748b;">Boundary vertices:</span> ${feature.properties.points_count}
            </div>
          `);
        },
      });
      layer.addTo(map);
      catchmentsLayerRef.current = layer;
    }
  }, [catchmentsGeoJSON, showCatchments]);

  // Update Incidents
  useEffect(() => {
    const layer = incidentsLayerRef.current;
    if (!layer) return;
    layer.clearLayers();

    if (!showIncidents) return;

    incidents.forEach((inc) => {
      if (!inc.latitude || !inc.longitude) return;

      const isCritical = inc.severity.toUpperCase() === 'CRITICAL';
      const isHigh = inc.severity.toUpperCase() === 'HIGH';
      const color = isCritical ? '#ef4444' : isHigh ? '#f97316' : '#eab308';

      // SVG Pulse Marker
      const icon = L.divIcon({
        className: 'custom-incident-pin',
        html: `
          <div style="
            background-color: ${color};
            width: 22px;
            height: 22px;
            border-radius: 50%;
            border: 2px solid #ffffff;
            box-shadow: 0 0 10px ${color};
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            cursor: pointer;
          ">
            !
          </div>
        `,
        iconSize: [22, 22],
        iconAnchor: [11, 11],
      });

      const marker = L.marker([inc.latitude, inc.longitude], { icon });
      marker.bindPopup(`
        <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4; min-width: 180px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <strong style="color: #0f172a;">${inc.id}</strong>
            <span style="background: ${color}20; color: ${color}; font-size: 10px; font-weight: bold; padding: 2px 6px; border-radius: 4px;">
              ${inc.severity}
            </span>
          </div>
          <div style="font-weight: 600; color: #1e293b; margin-bottom: 4px;">${inc.title}</div>
          <div style="color: #64748b; font-size: 12px; margin-bottom: 6px;">📍 ${inc.area}</div>
          <div style="color: #475569; font-size: 12px;"><strong>People affected:</strong> ${inc.people_affected}</div>
          <div style="color: #475569; font-size: 12px;"><strong>Status:</strong> ${inc.status}</div>
          <div style="color: #475569; font-size: 12px;"><strong>Source:</strong> ${inc.source}</div>
        </div>
      `);

      marker.on('click', () => {
        if (onSelectIncident) onSelectIncident(inc);
      });

      marker.addTo(layer);
    });
  }, [incidents, showIncidents, onSelectIncident]);

  // Update Teams
  useEffect(() => {
    const layer = teamsLayerRef.current;
    if (!layer) return;
    layer.clearLayers();

    if (!showTeams) return;

    teams.forEach((team) => {
      if (!team.latitude || !team.longitude) return;

      const isAvail = team.status === 'AVAILABLE';
      const color = isAvail ? '#3b82f6' : '#8b5cf6';

      const icon = L.divIcon({
        className: 'custom-team-pin',
        html: `
          <div style="
            background-color: ${color};
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 2px solid #ffffff;
            box-shadow: 0 0 8px ${color};
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
          ">
            ✚
          </div>
        `,
        iconSize: [20, 20],
        iconAnchor: [10, 10],
      });

      const marker = L.marker([team.latitude, team.longitude], { icon });
      marker.bindPopup(`
        <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
          <strong style="color: ${color};">${team.name} (${team.callsign})</strong><br/>
          <span style="color: #64748b;">Vehicle:</span> ${team.vehicle_type}<br/>
          <span style="color: #64748b;">Status:</span> ${team.status}<br/>
          <span style="color: #64748b;">Members:</span> ${team.members_count} personnel<br/>
          <span style="color: #64748b;">Base:</span> ${team.base_station}<br/>
          <span style="color: #64748b;">Contact:</span> ${team.contact_number}
        </div>
      `);
      marker.addTo(layer);
    });
  }, [teams, showTeams]);

  // Update Facilities & Shelters
  useEffect(() => {
    const layer = facilitiesLayerRef.current;
    if (!layer) return;
    layer.clearLayers();

    if (!showFacilities) return;

    facilities.forEach((fac) => {
      if (!fac.latitude || !fac.longitude) return;

      const isHosp = fac.facility_type === 'HOSPITAL';
      const color = isHosp ? '#ec4899' : '#10b981';

      const icon = L.divIcon({
        className: 'custom-facility-pin',
        html: `
          <div style="
            background-color: ${color};
            width: 18px;
            height: 18px;
            border-radius: 50%;
            border: 2px solid #ffffff;
            box-shadow: 0 0 6px ${color};
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-size: 10px;
          ">
            ${isHosp ? 'H' : 'S'}
          </div>
        `,
        iconSize: [18, 18],
        iconAnchor: [9, 9],
      });

      const marker = L.marker([fac.latitude, fac.longitude], { icon });
      const availBeds = fac.total_capacity - fac.current_occupancy;
      marker.bindPopup(`
        <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
          <strong style="color: ${color};">${fac.name}</strong><br/>
          <span style="color: #64748b;">Type:</span> ${fac.facility_type}<br/>
          <span style="color: #64748b;">Capacity:</span> ${fac.current_occupancy} / ${fac.total_capacity} beds<br/>
          <span style="color: #10b981; font-weight: 600;">Available: ${availBeds} spots</span><br/>
          <span style="color: #64748b;">Address:</span> ${fac.address}<br/>
          <span style="color: #64748b;">Contact:</span> ${fac.contact}
        </div>
      `);
      marker.addTo(layer);
    });
  }, [facilities, showFacilities]);

  // Update River Gauges
  useEffect(() => {
    const layer = gaugesLayerRef.current;
    if (!layer) return;
    layer.clearLayers();

    if (!showGauges) return;

    gauges.forEach((gauge) => {
      if (!gauge.latitude || !gauge.longitude) return;

      const icon = L.divIcon({
        className: 'custom-gauge-pin',
        html: `
          <div style="
            background-color: #0284c7;
            width: 16px;
            height: 16px;
            transform: rotate(45deg);
            border: 1px solid #ffffff;
            box-shadow: 0 0 5px #0284c7;
          "></div>
        `,
        iconSize: [16, 16],
        iconAnchor: [8, 8],
      });

      const marker = L.marker([gauge.latitude, gauge.longitude], { icon });
      marker.bindPopup(`
        <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
          <strong style="color: #0284c7;">${gauge.station_name} River Gauge</strong><br/>
          <span style="color: #64748b;">River:</span> ${gauge.river}<br/>
          <span style="color: #64748b;">Basin:</span> ${gauge.basin}<br/>
          <span style="color: #64748b;">Warning Threshold:</span> ${gauge.warning_level_m} m<br/>
          <span style="color: #ef4444;">Danger Threshold:</span> ${gauge.danger_level_m} m<br/>
          <span style="color: #64748b;">Gauge ID:</span> ${gauge.gauge_id}
        </div>
      `);
      marker.addTo(layer);
    });
  }, [gauges, showGauges]);

  // Update Geo-targeted Alerts (Circles)
  useEffect(() => {
    const layer = alertsLayerRef.current;
    if (!layer) return;
    layer.clearLayers();

    if (!showAlerts) return;

    alerts.forEach((alert) => {
      if (!alert.latitude || !alert.longitude) return;
      if (alert.status === 'RESOLVED') return;

      const isCritical = alert.severity === 'CRITICAL';
      const color = isCritical ? '#ef4444' : '#f97316';

      const circle = L.circle([alert.latitude, alert.longitude], {
        radius: alert.radius_km * 1000,
        color,
        fillColor: color,
        fillOpacity: 0.18,
        weight: 2,
        dashArray: '4, 6',
      });

      circle.bindPopup(`
        <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
          <span style="background: ${color}; color: #fff; font-size: 10px; font-weight: bold; padding: 2px 6px; border-radius: 4px;">
            ALERT RADIUS: ${alert.radius_km} KM
          </span>
          <div style="font-weight: bold; margin-top: 6px; color: #0f172a;">${alert.title}</div>
          <div style="color: #475569; font-size: 12px; margin: 4px 0;">${alert.message}</div>
          <div style="color: #64748b; font-size: 11px;">📍 Target Area: ${alert.area} | Acks: ${alert.acknowledged_count}</div>
        </div>
      `);

      circle.addTo(layer);
    });
  }, [alerts, showAlerts]);

  // Pan to selected incident
  useEffect(() => {
    if (selectedIncident && mapInstanceRef.current) {
      mapInstanceRef.current.setView([selectedIncident.latitude, selectedIncident.longitude], 14, {
        animate: true,
      });
    }
  }, [selectedIncident]);

  const handleResetView = () => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.setView([12.9716, 77.5946], 11, { animate: true });
    }
  };

  return (
    <div className="relative-map-container" style={{ position: 'relative', height, width: '100%', borderRadius: '8px', overflow: 'hidden' }}>
      <div ref={mapContainerRef} style={{ height: '100%', width: '100%' }} />

      {/* Layer Control Overlay Bar */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          left: 12,
          zIndex: 1000,
          background: 'rgba(15, 23, 42, 0.92)',
          backdropFilter: 'blur(8px)',
          padding: '8px 12px',
          borderRadius: '8px',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          display: 'flex',
          gap: '12px',
          alignItems: 'center',
          fontSize: '12px',
          color: '#cbd5e1',
          boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
        }}
      >
        {tileError && (
          <div
            style={{
              background: '#7f1d1d',
              color: '#fecaca',
              padding: '2px 8px',
              borderRadius: '4px',
              fontWeight: 600,
              fontSize: '11px',
            }}
            title="External tile network unreachable. Local vector overlays, catchments, and pins are displayed."
          >
            Offline Tiles Mode
          </div>
        )}
        <button
          onClick={handleResetView}
          style={{
            background: '#0284c7',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
            padding: '4px 8px',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '11px',
          }}
          title="Zoom to Bengaluru City"
        >
          ⌖ Bengaluru
        </button>

        <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showCatchments}
            onChange={(e) => setShowCatchments(e.target.checked)}
          />
          <span style={{ color: '#06b6d4' }}>●</span> Catchments ({catchmentsGeoJSON?.features?.length || 0})
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showIncidents}
            onChange={(e) => setShowIncidents(e.target.checked)}
          />
          <span style={{ color: '#ef4444' }}>●</span> Incidents ({incidents.length})
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showTeams}
            onChange={(e) => setShowTeams(e.target.checked)}
          />
          <span style={{ color: '#3b82f6' }}>✚</span> Teams ({teams.length})
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showFacilities}
            onChange={(e) => setShowFacilities(e.target.checked)}
          />
          <span style={{ color: '#10b981' }}>●</span> Shelters ({facilities.length})
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showGauges}
            onChange={(e) => setShowGauges(e.target.checked)}
          />
          <span style={{ color: '#0284c7' }}>◆</span> Gauges ({gauges.length})
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showAlerts}
            onChange={(e) => setShowAlerts(e.target.checked)}
          />
          <span style={{ color: '#f97316' }}>◎</span> Alerts ({alerts.filter((a) => a.status === 'ACTIVE').length})
        </label>
      </div>

      {/* Map Legend Footer */}
      <div
        style={{
          position: 'absolute',
          bottom: 10,
          left: 12,
          zIndex: 1000,
          background: 'rgba(15, 23, 42, 0.85)',
          padding: '4px 10px',
          borderRadius: '4px',
          fontSize: '11px',
          color: '#94a3b8',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          pointerEvents: 'none',
        }}
      >
        IndoFloods Catchments GIS & IndoFloods Gauge Network · Interactive GeoJSON Layer
      </div>
    </div>
  );
};
