import React, { useState } from 'react';
import { cleanMessage, toast } from '../../lib/toast';
import { api } from '../../api/client';
import type { Incident, RescueTeam } from '../../api/types';
import { Plus } from 'lucide-react';
import { Button, DataNotice, Dialog, PageHeader, SearchField, SelectField, SeverityBadge } from '../ui';
import { INCIDENT_STATES, actionsFor, humanStatus, needsCommanderApproval, statusPillClass } from '../../lib/lifecycle';
import type { LifecycleAction } from '../../lib/lifecycle';

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
  const [query, setQuery] = useState('');

  const statuses = INCIDENT_STATES;
  const availableTeams = teams.filter((t) => t.status === 'AVAILABLE');

  const openAssign = (inc: Incident) => {
    setAssignTeamModal(inc);
    setSelectedTeamId(availableTeams[0]?.id || '');
  };

  const handleStatusTransition = async (incId: string, newStatus: string) => {
    try {
      await api.changeIncidentState(incId, newStatus, { actor: 'operator' });
      setActionNotice(`Incident ${incId} moved to ${humanStatus(newStatus)}.`);
      onRefresh();
    } catch (err: any) {
      toast.error(cleanMessage(err));
    }
  };

  const handleTriage = async (inc: Incident) => {
    try {
      const task = await api.executeSupervisorTriage({ task_type: 'RESCUE_DISPATCH', incident_id: inc.id });
      setActionNotice(
        task.requires_human_approval
          ? `Supervisor task ${task.id} created. ${inc.id} is waiting for commander approval in the Supervisor view.`
          : `Supervisor task ${task.id} completed for ${inc.id}.`,
      );
      onRefresh();
    } catch (err: any) {
      toast.error(cleanMessage(err));
    }
  };

  const runAction = (inc: Incident, a: LifecycleAction) => {
    if (a.kind === 'dispatch') return openAssign(inc);
    if (a.kind === 'triage') return handleTriage(inc);
    if (a.to) return handleStatusTransition(inc.id, a.to);
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
      toast.error(cleanMessage(err));
    }
  };

  const filteredIncidents = incidents.filter((inc) => {
    if (filterStatus !== 'ALL' && inc.status !== filterStatus) return false;
    if (filterSeverity !== 'ALL' && inc.severity !== filterSeverity) return false;
    const q = query.trim().toLowerCase();
    if (q && !`${inc.id} ${inc.title} ${inc.area} ${inc.assigned_team_id ?? ''}`.toLowerCase().includes(q)) return false;
    return true;
  });

  return (
    <div className="rescue-ops-container">
      <PageHeader title="Rescue operations"
        description="Incident lifecycle: reported, verified, queued, triage, pending approval, dispatched, in transit, on scene, resolved. Incidents with five or more victims, or HIGH or CRITICAL severity, are dispatched only after commander approval. Nothing is dispatched automatically."
        actions={<Button variant="primary" icon={<Plus size={16} />} onClick={onOpenReportModal}>Report emergency incident</Button>} />
      <DataNotice items={incidents} noun="incidents" />
      {actionNotice && (
        <div className="notice-banner banner-success">
          <span>{actionNotice}</span>
          <button className="btn-close" onClick={() => setActionNotice(null)}>✕</button>
        </div>
      )}

      {/* Deployment Teams Strip */}
      <div className="teams-strip">
        <h4 style={{ margin: '0 0 10px 0', fontSize: '12px', color: 'var(--rn-text-dim)' }}>
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
      <div className="filter-bar ops-filters">
        <SearchField value={query} onChange={setQuery} label="Search incidents" placeholder="Search by ID, title, area or squad" />
        <div className="filter-group">
          <span>Status:</span>
          {['ALL', ...statuses].map((st) => (
            <button
              key={st}
              className={`filter-btn ${filterStatus === st ? 'active' : ''}`}
              onClick={() => setFilterStatus(st)}
            >
              {humanStatus(st)}
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
                <tr key={inc.id} className={['RESOLVED', 'DUPLICATE', 'CANCELLED'].includes(inc.status) ? 'row-resolved' : ''}>
                  <td className="font-mono font-bold text-cyan">{inc.id}</td>
                  <td>
                    <strong>{inc.title}</strong>
                    <div className="text-muted" style={{ fontSize: '11px' }}>📍 {inc.area}</div>
                  </td>
                  <td>
                    <SeverityBadge severity={inc.severity} />
                  </td>
                  <td>
                    <span className="font-mono font-bold">{inc.people_affected}</span>
                  </td>
                  <td className="text-xs text-muted font-mono">
                    {inc.source}
                    {inc.data_label && <div style={{ fontSize: '10px', marginTop: '2px' }}>[{inc.data_label}]</div>}
                  </td>
                  <td>
                    {inc.assigned_team_id ? (
                      <span className="badge-team">{inc.assigned_team_id}</span>
                    ) : inc.status === 'DISPATCHED' ? (
                      <button className="btn-outline btn-xs text-cyan" onClick={() => openAssign(inc)}>
                        + Assign Squad
                      </button>
                    ) : (
                      <span className="text-muted text-xs">—</span>
                    )}
                  </td>
                  <td>
                    <span className={`status-pill ${statusPillClass(inc.status)}`}>
                      {humanStatus(inc.status)}
                    </span>
                    {needsCommanderApproval(inc) && !['RESOLVED', 'DUPLICATE', 'CANCELLED'].includes(inc.status) && (
                      <div className="text-xs text-orange" style={{ marginTop: '2px' }}>approval gate</div>
                    )}
                  </td>
                  <td>
                    <div className="action-button-group">
                      {actionsFor(inc).map((a) => (
                        <button
                          key={a.label}
                          className={`btn-secondary btn-xs ${a.tone ? `text-${a.tone}` : ''}`}
                          onClick={() => runAction(inc, a)}
                        >
                          {a.label}
                        </button>
                      ))}
                      {inc.status === 'PENDING_APPROVAL' && (
                        <span className="text-xs text-orange">Awaiting commander (Supervisor view)</span>
                      )}
                      {['RESOLVED', 'DUPLICATE', 'CANCELLED'].includes(inc.status) && (
                        <span className="text-muted text-xs">Closed</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Dispatch confirmation: the server still enforces the approval gate and atomic dispatch (P0). */}
      <Dialog open={Boolean(assignTeamModal)} title={`Dispatch a squad to ${assignTeamModal?.id ?? ''}`} onClose={() => setAssignTeamModal(null)}
        footer={<><Button onClick={() => setAssignTeamModal(null)}>Cancel</Button><Button variant="primary" onClick={handleAssignTeam} disabled={!selectedTeamId}>Confirm dispatch</Button></>}>
        {assignTeamModal && (
          <div className="ops-dispatch">
            <p><strong>Location:</strong> {assignTeamModal.area} ({assignTeamModal.title})<br /><strong>People affected:</strong> {assignTeamModal.people_affected}</p>
            {availableTeams.length === 0
              ? <p className="auth-notice auth-notice-warn" role="alert">No squad is available right now.</p>
              : (
                <SelectField label="Response squad" value={selectedTeamId} onChange={(e) => setSelectedTeamId(e.target.value)}>
                  {availableTeams.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.callsign}) · {t.vehicle_type}</option>)}
                </SelectField>
              )}
          </div>
        )}
      </Dialog>
    </div>
  );
};
