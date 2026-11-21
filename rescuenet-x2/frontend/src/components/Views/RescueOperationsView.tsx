import React, { useState } from 'react';
import { api } from '../../api/client';
import type { Incident, RescueTeam } from '../../api/types';
import { Plus } from 'lucide-react';

interface RescueOperationsViewProps {
  incidents: Incident[];
  teams: RescueTeam[];
  onRefresh: () => void;
  onOpenReportModal: () => void;
}

export const RescueOperationsView: React.FC<RescueOperationsViewProps> = ({
  incidents,
  teams,
  onRefresh,
  onOpenReportModal,
}) => {
  const [assignTeamModal, setAssignTeamModal] = useState<Incident | null>(null);
  const [selectedTeamId, setSelectedTeamId] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [filterSeverity, setFilterSeverity] = useState<string>('ALL');
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const statuses = ['REPORTED', 'VERIFIED', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED'];

  const handleStatusTransition = async (incId: string, newStatus: string) => {
    try {
      await api.updateIncident(incId, { status: newStatus });
      setActionNotice(`Incident ${incId} transitioned to ${newStatus}.`);
      onRefresh();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleAssignTeam = async () => {
    if (!assignTeamModal || !selectedTeamId) return;
    try {
      await api.assignTeam(selectedTeamId, assignTeamModal.id);
      setActionNotice(`Team ${selectedTeamId} assigned to ${assignTeamModal.id}.`);
      setAssignTeamModal(null);
      setSelectedTeamId('');
      onRefresh();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const filteredIncidents = incidents.filter((inc) => {
    if (filterStatus !== 'ALL' && inc.status !== filterStatus) return false;
    if (filterSeverity !== 'ALL' && inc.severity !== filterSeverity) return false;
    return true;
  });

  return (
    <div className="rescue-ops-container">
      <div className="view-header">
        <div>
          <h2>Rescue Operations & Incident Dispatch Command</h2>
          <p>
            Track lifecycle transitions: <code>REPORTED → VERIFIED → ASSIGNED → IN_PROGRESS → RESOLVED</code>.
            Dispatch specialized NDRF, SDRF, and Civil Defense boat squads.
          </p>
        </div>
        <button className="btn-primary" onClick={onOpenReportModal}>
          <Plus size={16} /> Report Emergency Incident
        </button>
      </div>

      {actionNotice && (
        <div className="notice-banner banner-success">
          <span>{actionNotice}</span>
          <button className="btn-close" onClick={() => setActionNotice(null)}>✕</button>
        </div>
      )}

      {/* Deployment Teams Strip */}
      <div className="teams-strip">
        <h4 style={{ margin: '0 0 10px 0', fontSize: '12px', color: '#94a3b8' }}>
          ACTIVE RESCUE SQUADS ({teams.filter((t) => t.status === 'AVAILABLE').length} AVAILABLE / {teams.length} TOTAL)
        </h4>
        <div className="teams-grid">
          {teams.map((t) => (
            <div key={t.id} className="team-pill-card">
              <div className="team-pill-top">
                <span className="font-mono text-cyan font-bold">{t.callsign}</span>
                <span className={`status-pill ${t.status === 'AVAILABLE' ? 'pill-active' : 'pill-deployed'}`}>
                  {t.status}
                </span>
              </div>
              <div className="team-pill-name">{t.name}</div>
              <div className="team-pill-meta">
                <span>{t.vehicle_type}</span> · <span>👥 {t.members_count}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Filter Bar */}
      <div className="filter-bar">
        <div className="filter-group">
          <span>Status:</span>
          {['ALL', ...statuses].map((st) => (
            <button
              key={st}
              className={`filter-btn ${filterStatus === st ? 'active' : ''}`}
              onClick={() => setFilterStatus(st)}
            >
              {st}
            </button>
          ))}
        </div>

        <div className="filter-group">
          <span>Severity:</span>
          {['ALL', 'CRITICAL', 'HIGH', 'MODERATE', 'LOW'].map((sev) => (
            <button
              key={sev}
              className={`filter-btn ${filterSeverity === sev ? 'active' : ''}`}
              onClick={() => setFilterSeverity(sev)}
            >
              {sev}
            </button>
          ))}
        </div>
      </div>

      {/* Kanban / Incident Board */}
      <div className="incidents-table-panel panel">
        <div className="panel-title-bar">
          <div>
            <h3>Operational Incident Registry</h3>
            <p>{filteredIncidents.length} persistent incidents matching current filters</p>
          </div>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>LOCATION</th>
                <th>SEVERITY</th>
                <th>AFFECTED</th>
                <th>SOURCE</th>
                <th>ASSIGNED TEAM</th>
                <th>CURRENT STATUS</th>
                <th>LIFECYCLE ACTION</th>
              </tr>
            </thead>
            <tbody>
              {filteredIncidents.map((inc) => (
                <tr key={inc.id} className={inc.status === 'RESOLVED' ? 'row-resolved' : ''}>
                  <td className="font-mono font-bold text-cyan">{inc.id}</td>
                  <td>
                    <strong>{inc.title}</strong>
                    <div className="text-muted" style={{ fontSize: '11px' }}>📍 {inc.area}</div>
                  </td>
                  <td>
                    <span className={`pill-alert-${inc.severity.toLowerCase()}`}>
                      {inc.severity}
                    </span>
                  </td>
                  <td>
                    <span className="font-mono font-bold">{inc.people_affected}</span>
                  </td>
                  <td className="text-xs text-muted font-mono">{inc.source}</td>
                  <td>
                    {inc.assigned_team_id ? (
                      <span className="badge-team">{inc.assigned_team_id}</span>
                    ) : (
                      <button
                        className="btn-outline btn-xs text-cyan"
                        onClick={() => {
                          setAssignTeamModal(inc);
                          setSelectedTeamId(teams[0]?.id || '');
                        }}
                      >
                        + Assign Squad
                      </button>
                    )}
                  </td>
                  <td>
                    <span className={`status-pill pill-${inc.status.toLowerCase()}`}>
                      {inc.status}
                    </span>
                  </td>
                  <td>
                    <div className="action-button-group">
                      {inc.status === 'REPORTED' && (
                        <button
                          className="btn-secondary btn-xs"
                          onClick={() => handleStatusTransition(inc.id, 'VERIFIED')}
                        >
                          Verify ✓
                        </button>
                      )}
                      {inc.status === 'VERIFIED' && (
                        <button
                          className="btn-secondary btn-xs text-cyan"
                          onClick={() => {
                            setAssignTeamModal(inc);
                            setSelectedTeamId(teams[0]?.id || '');
                          }}
                        >
                          Dispatch Team
                        </button>
                      )}
                      {inc.status === 'ASSIGNED' && (
                        <button
                          className="btn-secondary btn-xs text-orange"
                          onClick={() => handleStatusTransition(inc.id, 'IN_PROGRESS')}
                        >
                          Begin Rescue ➔
                        </button>
                      )}
                      {inc.status === 'IN_PROGRESS' && (
                        <button
                          className="btn-secondary btn-xs text-emerald"
                          onClick={() => handleStatusTransition(inc.id, 'RESOLVED')}
                        >
                          Mark Resolved ✓
                        </button>
                      )}
                      {inc.status === 'RESOLVED' && (
                        <span className="text-muted text-xs">Completed</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal: Assign Team */}
      {assignTeamModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <div className="modal-header">
              <h3>Dispatch Rescue Squad to Incident {assignTeamModal.id}</h3>
              <button className="icon-btn" onClick={() => setAssignTeamModal(null)}>✕</button>
            </div>
            <div style={{ padding: '16px' }}>
              <div style={{ marginBottom: '12px' }}>
                <strong>Location:</strong> {assignTeamModal.area} ({assignTeamModal.title})<br/>
                <strong>Trapped Persons:</strong> {assignTeamModal.people_affected}
              </div>

              <label style={{ display: 'block', marginBottom: '8px' }}>
                Select Response Team:
                <select
                  className="select-input"
                  style={{ width: '100%', marginTop: '6px' }}
                  value={selectedTeamId}
                  onChange={(e) => setSelectedTeamId(e.target.value)}
                >
                  {teams.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.callsign}) — {t.vehicle_type} [{t.status}]
                    </option>
                  ))}
                </select>
              </label>

              <div className="modal-actions" style={{ marginTop: '20px' }}>
                <button className="btn-secondary" onClick={() => setAssignTeamModal(null)}>
                  Cancel
                </button>
                <button className="btn-primary" onClick={handleAssignTeam}>
                  Confirm Dispatch
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
