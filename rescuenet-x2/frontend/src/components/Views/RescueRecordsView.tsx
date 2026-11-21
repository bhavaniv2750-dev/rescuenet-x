import React, { useState, useEffect } from 'react';
import { cleanMessage, toast } from '../../lib/toast';
import { api } from '../../api/client';
import type { RescueRecord } from '../../api/types';
import { Award, Plus, Download, HeartHandshake } from 'lucide-react';

export const RescueRecordsView: React.FC = () => {
  const [records, setRecords] = useState<RescueRecord[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [showAddModal, setShowAddModal] = useState(false);

  // Form
  const [incidentId, setIncidentId] = useState('INC-1042');
  const [teamId, setTeamId] = useState('TEAM-NDRF-10');
  const [location, setLocation] = useState('Devasandra Lowlands, KR Puram');
  const [peopleRescued, setPeopleRescued] = useState(12);
  const [survivors, setSurvivors] = useState(12);
  const [severeInjuries, setSevereInjuries] = useState(1);
  const [minorInjuries, setMinorInjuries] = useState(3);
  const [notes, setNotes] = useState('Successfully completed evacuation of 3 residential clusters using inflatable boat.');
  const missing = 0;
  const deceased = 0;

  const fetchRecords = async () => {
    try {
      const [recs, sum] = await Promise.all([
        api.getRecords(),
        api.getRecordsSummary(),
      ]);
      setRecords(recs.items);
      setSummary(sum);
    } catch (err: any) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchRecords();
  }, []);

  const handleCreateRecord = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createRecord({
        incident_id: incidentId,
        team_id: teamId,
        location,
        people_rescued: peopleRescued,
        survivors,
        missing,
        deceased,
        severe_injuries: severeInjuries,
        minor_injuries: minorInjuries,
        notes,
      });
      setShowAddModal(false);
      fetchRecords();
    } catch (err: any) {
      toast.error(cleanMessage(err));
    }
  };

  const [exporting, setExporting] = useState(false);

  const handleExportCSV = async () => {
    if (records.length === 0) {
      toast.error('No rescue mission records available to export.');
      return;
    }

    setExporting(true);
    try {
      // 1. Attempt official backend CSV endpoint
      const response = await fetch(api.getRecordsCSVUrl());
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `RescueNet_Missions_Archive_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        return;
      }
    } catch (err) {
      console.warn('Backend CSV endpoint unreachable, using client-side generator', err);
    } finally {
      setExporting(false);
    }

    // 2. Client-side RFC-4180 compliant CSV generator fallback
    const escapeCsv = (val: any) => {
      if (val === null || val === undefined) return '""';
      const str = String(val).replace(/"/g, '""');
      return `"${str}"`;
    };

    const headers = [
      'Record ID',
      'Incident ID',
      'Rescue Team ID',
      'Operational Location',
      'People Rescued',
      'Survivors',
      'Missing Persons',
      'Deceased Count',
      'Severe Injuries',
      'Minor Injuries',
      'Mission Debrief Notes',
      'Completion Timestamp',
    ];

    const rows = records.map((r) => [
      escapeCsv(r.id),
      escapeCsv(r.incident_id),
      escapeCsv(r.team_id),
      escapeCsv(r.location),
      r.people_rescued,
      r.survivors,
      r.missing,
      r.deceased,
      r.severe_injuries,
      r.minor_injuries,
      escapeCsv(r.notes),
      escapeCsv(r.completed_at),
    ]);

    const csvContent = '\uFEFF' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `RescueNet_Missions_Archive_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="records-container">
      <div className="view-header">
        <div>
          <h2>Operational Rescue Records & Mission Outcomes</h2>
          <p>
            Certified mission debrief logs, survivor tallies, casualty tracking, and responder assignment records.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn-secondary" onClick={handleExportCSV} disabled={exporting}>
            <Download size={16} className={exporting ? 'spin' : ''} />
            {exporting ? 'Generating CSV...' : 'Export CSV Report'}
          </button>
          <button className="btn-primary" onClick={() => setShowAddModal(true)}>
            <Plus size={16} /> Log Mission Outcome
          </button>
        </div>
      </div>

      {/* Aggregate KPI Strip */}
      <div className="metrics-grid">
        <div className="metric-card border-emerald">
          <div className="metric-header">
            <span>TOTAL LIVES RESCUED</span>
            <HeartHandshake className="text-emerald" size={18} />
          </div>
          <div className="metric-body">
            <span className="metric-number text-emerald">{summary?.total_rescued || 0}</span>
          </div>
          <div className="metric-footer">{summary?.total_survivors || 0} confirmed safe survivors</div>
        </div>

        <div className="metric-card border-blue">
          <div className="metric-header">
            <span>COMPLETED MISSIONS</span>
            <Award className="text-blue" size={18} />
          </div>
          <div className="metric-body">
            <span className="metric-number">{summary?.total_missions || 0}</span>
          </div>
          <div className="metric-footer">Across all participating agencies</div>
        </div>

        <div className="metric-card border-yellow">
          <div className="metric-header">
            <span>INJURIES TREATED</span>
            <span className="font-mono text-yellow font-bold">MED</span>
          </div>
          <div className="metric-body">
            <span className="metric-number text-yellow">
              {(summary?.total_severe_injuries || 0) + (summary?.total_minor_injuries || 0)}
            </span>
          </div>
          <div className="metric-footer">{summary?.total_severe_injuries || 0} severe, {summary?.total_minor_injuries || 0} minor</div>
        </div>

        <div className="metric-card border-red">
          <div className="metric-header">
            <span>CASUALTIES / MISSING</span>
            <span className="font-mono text-red font-bold">CRIT</span>
          </div>
          <div className="metric-body">
            <span className="metric-number text-red">
              {(summary?.total_missing || 0) + (summary?.total_deceased || 0)}
            </span>
          </div>
          <div className="metric-footer">{summary?.total_missing || 0} missing, {summary?.total_deceased || 0} deceased</div>
        </div>
      </div>

      {/* Records Table */}
      <div className="panel records-table-card">
        <div className="panel-title-bar">
          <div>
            <h3>Archived Rescue Mission Logs</h3>
            <p>{records.length} persistent debrief records in SQLite</p>
          </div>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>RECORD ID</th>
                <th>INCIDENT LINK</th>
                <th>SQUAD ID</th>
                <th>MISSION LOCATION</th>
                <th>RESCUED</th>
                <th>SURVIVORS</th>
                <th>INJURIES</th>
                <th>CASUALTIES</th>
                <th>COMPLETED AT</th>
              </tr>
            </thead>
            <tbody>
              {records.map((rec) => (
                <tr key={rec.id}>
                  <td className="font-mono text-cyan font-bold">{rec.id}</td>
                  <td className="font-mono text-xs">{rec.incident_id}</td>
                  <td><span className="badge-team">{rec.team_id}</span></td>
                  <td>📍 {rec.location}</td>
                  <td className="font-mono font-bold text-emerald">{rec.people_rescued}</td>
                  <td className="font-mono">{rec.survivors}</td>
                  <td className="text-xs">
                    Sev: {rec.severe_injuries} | Min: {rec.minor_injuries}
                  </td>
                  <td className="text-xs font-mono">
                    {rec.missing > 0 || rec.deceased > 0 ? (
                      <span className="text-red font-bold">Miss: {rec.missing} | Dec: {rec.deceased}</span>
                    ) : (
                      <span className="text-emerald">0 (None)</span>
                    )}
                  </td>
                  <td className="text-xs text-muted font-mono">
                    {new Date(rec.completed_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal: Add Record */}
      {showAddModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <div className="modal-header">
              <h3>Log Certified Rescue Mission Outcome</h3>
              <button className="icon-btn" onClick={() => setShowAddModal(false)}>✕</button>
            </div>
            <form onSubmit={handleCreateRecord} className="modal-form">
              <div className="form-row">
                <label>
                  Incident ID
                  <input required value={incidentId} onChange={(e) => setIncidentId(e.target.value)} />
                </label>
                <label>
                  Rescue Team
                  <input required value={teamId} onChange={(e) => setTeamId(e.target.value)} />
                </label>
              </div>

              <label>
                Mission Location
                <input required value={location} onChange={(e) => setLocation(e.target.value)} />
              </label>

              <div className="form-row">
                <label>
                  Total People Rescued
                  <input type="number" min="0" required value={peopleRescued} onChange={(e) => setPeopleRescued(parseInt(e.target.value) || 0)} />
                </label>
                <label>
                  Confirmed Survivors
                  <input type="number" min="0" required value={survivors} onChange={(e) => setSurvivors(parseInt(e.target.value) || 0)} />
                </label>
              </div>

              <div className="form-row">
                <label>
                  Severe Injuries
                  <input type="number" min="0" required value={severeInjuries} onChange={(e) => setSevereInjuries(parseInt(e.target.value) || 0)} />
                </label>
                <label>
                  Minor Injuries
                  <input type="number" min="0" required value={minorInjuries} onChange={(e) => setMinorInjuries(parseInt(e.target.value) || 0)} />
                </label>
              </div>

              <label>
                Mission Notes & Debrief
                <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
              </label>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowAddModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Save Certified Record
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
