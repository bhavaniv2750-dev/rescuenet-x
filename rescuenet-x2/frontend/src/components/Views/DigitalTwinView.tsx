import React, { useState } from 'react';
import type { Facility, Incident, RescueTeam, RiverGauge } from '../../api/types';
import { InteractiveMap } from '../Map/InteractiveMap';
import { Layers, MapPin, Waves } from 'lucide-react';

interface DigitalTwinViewProps {
  catchmentsGeoJSON: any;
  incidents: Incident[];
  teams: RescueTeam[];
  facilities: Facility[];
  gauges: RiverGauge[];
  alerts: any[];
}

export const DigitalTwinView: React.FC<DigitalTwinViewProps> = ({
  catchmentsGeoJSON,
  incidents,
  teams,
  facilities,
  gauges,
  alerts,
}) => {
  const [selectedGauge, setSelectedGauge] = useState<RiverGauge | null>(null);
  const [filterRiver, setFilterRiver] = useState<string>('ALL');

  const uniqueRivers = ['ALL', ...Array.from(new Set(gauges.map((g) => g.river || 'Other')))];

  const filteredGauges = filterRiver === 'ALL'
    ? gauges
    : gauges.filter((g) => g.river === filterRiver);

  return (
    <div className="digital-twin-container">
      <div className="view-header">
        <div>
          <h2>Flood Digital Twin · GIS Intelligence</h2>
          <p>
            Real IndoFloods river catchment polygons, Central Water Commission gauge telemetry,
            and RescueNet operational assets across Karnataka.
          </p>
        </div>
        <div className="stats-badges">
          <span className="badge"><Layers size={14} /> {catchmentsGeoJSON?.features?.length || 5} Catchments</span>
          <span className="badge"><Waves size={14} /> {gauges.length} River Gauges</span>
          <span className="badge"><MapPin size={14} /> {incidents.length} Active Pins</span>
        </div>
      </div>

      <div className="twin-layout-grid">
        {/* Full-width Map Canvas */}
        <div className="panel map-full-card">
          <InteractiveMap
            incidents={incidents}
            teams={teams}
            facilities={facilities}
            gauges={filteredGauges}
            catchmentsGeoJSON={catchmentsGeoJSON}
            alerts={alerts}
            height="560px"
            center={selectedGauge ? [selectedGauge.latitude, selectedGauge.longitude] : [12.9716, 77.5946]}
            zoom={selectedGauge ? 13 : 10}
          />
        </div>

        {/* River Gauge Telemetry Table */}
        <div className="panel gauge-table-card">
          <div className="panel-title-bar">
            <div>
              <h3>Karnataka River Monitoring Gauges</h3>
              <p>Warning & Danger threshold monitoring from IndoFloods</p>
            </div>
            <select
              className="select-input"
              value={filterRiver}
              onChange={(e) => setFilterRiver(e.target.value)}
              style={{ maxWidth: '200px' }}
            >
              {uniqueRivers.map((r) => (
                <option key={r} value={r}>
                  {r === 'ALL' ? 'All Rivers & Tributaries' : r}
                </option>
              ))}
            </select>
          </div>

          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>STATION</th>
                  <th>RIVER / BASIN</th>
                  <th>WARNING LVL</th>
                  <th>DANGER LVL</th>
                  <th>COORDINATES</th>
                  <th>STATUS</th>
                  <th>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {filteredGauges.slice(0, 10).map((gauge) => (
                  <tr key={gauge.gauge_id} className={selectedGauge?.gauge_id === gauge.gauge_id ? 'row-selected' : ''}>
                    <td>
                      <strong>{gauge.station_name}</strong>
                      <div className="text-muted font-mono" style={{ fontSize: '11px' }}>{gauge.gauge_id}</div>
                    </td>
                    <td>
                      <div>{gauge.river}</div>
                      <div className="text-muted" style={{ fontSize: '11px' }}>{gauge.basin}</div>
                    </td>
                    <td>
                      <span className="text-yellow font-mono font-bold">{gauge.warning_level_m} m</span>
                    </td>
                    <td>
                      <span className="text-red font-mono font-bold">{gauge.danger_level_m} m</span>
                    </td>
                    <td className="font-mono text-muted" style={{ fontSize: '11px' }}>
                      {gauge.latitude.toFixed(3)}, {gauge.longitude.toFixed(3)}
                    </td>
                    <td>
                      <span className="status-pill pill-active">MONITORING</span>
                    </td>
                    <td>
                      <button
                        className="btn-outline btn-xs"
                        onClick={() => setSelectedGauge(gauge)}
                      >
                        Locate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-footer-note">
            Showing 10 of {filteredGauges.length} stations. Coordinates mapped directly from IndoFloods dataset.
          </div>
        </div>
      </div>
    </div>
  );
};
