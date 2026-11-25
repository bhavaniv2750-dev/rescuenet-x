import React, { useState } from 'react';
import type { Facility, Incident, RescueTeam, RiverGauge } from '../../api/types';
import { InteractiveMap } from '../Map/InteractiveMap';
import { Button, DataTable, PageHeader, Panel, ProvenanceBadge, SelectField, StatusBadge } from '../ui';

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
      <PageHeader title="Flood digital twin"
        description="Geospatial flood intelligence and emergency response monitoring."
        meta={<>
          <ProvenanceBadge kind="HISTORICAL" /><span className="rn-field-hint">catchment boundaries</span>
          <ProvenanceBadge kind="UNAVAILABLE" /><span className="rn-field-hint">live water levels</span>
          {incidents.length > 0 && <><ProvenanceBadge kind="SIMULATED" /><span className="rn-field-hint">operational records</span></>}
        </>}
        actions={<><StatusBadge tone="info">{catchmentsGeoJSON?.features?.length ?? 0} catchments</StatusBadge><StatusBadge tone="info">{gauges.length} gauges</StatusBadge><StatusBadge tone="info">{incidents.length} incident pins</StatusBadge></>} />

      <details className="rn-about-data">
        <summary>About this data</summary>
        <ul>
          <li><strong>Catchment boundaries</strong> are historical outlines from the IndoFloods dataset. They show where water drains to, not where flooding is happening.</li>
          <li><strong>River gauges</strong> are listed with their warning and danger reference levels. No live water-level feed is connected, so current readings are unavailable.</li>
          <li><strong>Incidents, squads and shelters</strong> shown here are simulated demonstration records unless a record is marked as observed. They are not real emergencies.</li>
          <li><strong>No hydrological simulation:</strong> this page does not model water movement or inundation, and it has not been validated as a hydrodynamic model.</li>
          <li><strong>Base map:</strong> online map tiles when reachable; otherwise locally stored geography (Natural Earth and BBMP ward boundaries, or a regional archive if one is installed). Local coverage is limited to what those datasets contain, and map coverage does not imply operational or forecasting coverage.</li>
        </ul>
      </details>

      <div className="twin-layout-grid">
        <InteractiveMap incidents={incidents} teams={teams} facilities={facilities} gauges={filteredGauges} catchmentsGeoJSON={catchmentsGeoJSON} alerts={alerts}
          height="clamp(340px, 62vh, 680px)" center={selectedGauge ? [selectedGauge.latitude, selectedGauge.longitude] : [12.9716, 77.5946]} zoom={selectedGauge ? 13 : 10} />

        <Panel title="River gauge stations" actions={
          <SelectField label="River" value={filterRiver} onChange={(e) => setFilterRiver(e.target.value)}>
            {uniqueRivers.map((r) => <option key={r} value={r}>{r === 'ALL' ? 'All rivers and tributaries' : r}</option>)}
          </SelectField>} flush>
          <p className="rn-field-hint" style={{ padding: 'var(--sp-3) var(--sp-4) 0' }}>Warning and danger levels are reference thresholds from the dataset. No live water-level feed is connected, so a current reading is not available.</p>
          <DataTable caption="River gauge stations" rows={filteredGauges.slice(0, 10)} rowKey={(g) => g.gauge_id}
            columns={[
              { key: 's', header: 'Station', render: (g) => <><strong>{g.station_name}</strong><div className="rn-field-hint auth-mono">{g.gauge_id}</div></> },
              { key: 'r', header: 'River / basin', render: (g) => <>{g.river}<div className="rn-field-hint">{g.basin}</div></> },
              { key: 'w', header: 'Warning level', render: (g) => <span className="auth-mono">{g.warning_level_m} m</span> },
              { key: 'd', header: 'Danger level', render: (g) => <span className="auth-mono">{g.danger_level_m} m</span> },
              { key: 'l', header: 'Live reading', render: () => <ProvenanceBadge kind="UNAVAILABLE" /> },
              { key: 'a', header: 'Map', render: (g) => <Button size="sm" onClick={() => setSelectedGauge(g)} aria-label={`Locate ${g.station_name} on the map`}>Locate</Button> },
            ]} />
          <div className="rn-field-hint" style={{ padding: 'var(--sp-3) var(--sp-4)' }}>Showing {Math.min(10, filteredGauges.length)} of {filteredGauges.length} stations.</div>
        </Panel>
      </div>
    </div>
  );
};
