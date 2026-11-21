import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import type { Incident } from '../../api/types';
import { actionsFor, humanStatus, statusPillClass } from '../../lib/lifecycle';
import { cleanMessage, toast } from '../../lib/toast';

interface Props {
  /** citizen/volunteer: reports they filed.  officer: missions assigned to their team. */
  variant: 'reports' | 'missions';
  teamName?: string | null;
}

const FIELD_ACTIONS = new Set(['IN_TRANSIT', 'ON_SCENE', 'RESOLVED']);

export const MyWorkView: React.FC<Props> = ({ variant, teamName }) => {
  const [items, setItems] = useState<Incident[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems((await api.getMyIncidents()).items);
      setError(null);
    } catch (e) {
      setError(cleanMessage(e));
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]);

  const move = async (inc: Incident, to: string) => {
    try {
      await api.changeIncidentState(inc.id, to);
      toast.success(`${inc.id} is now ${humanStatus(to)}.`);
      load();
    } catch (e) {
      toast.error(cleanMessage(e));
    }
  };

  const missions = variant === 'missions';

  return (
    <div className="my-work">
      <div className="view-header">
        <div>
          <h2>{missions ? 'My Team’s Missions' : 'My Reports'}</h2>
          <p>
            {missions
              ? `Incidents dispatched to ${teamName || 'your team'}. Update the status as you move.`
              : 'Emergencies you reported, and what the rescue team has done about them.'}
          </p>
        </div>
        <button className="btn-secondary" onClick={load}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {error && <div className="form-notice form-notice-error">{error}</div>}

      {items === null && !error ? (
        <div className="skeleton-stack">
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      ) : items && items.length === 0 ? (
        <div className="empty-state panel">
          <strong>{missions ? 'No missions assigned' : 'No reports yet'}</strong>
          <span>{missions ? 'New assignments show up here after a commander approves a dispatch.' : 'When you report an emergency it appears here.'}</span>
        </div>
      ) : (
        <div className="card-list">
          {items?.map((inc) => (
            <article key={inc.id} className="work-card panel">
              <header>
                <span className="font-mono text-cyan font-bold">{inc.id}</span>
                <span className={`status-pill ${statusPillClass(inc.status)}`}>{humanStatus(inc.status)}</span>
              </header>
              <h4>{inc.title}</h4>
              <p className="text-muted">{inc.description}</p>
              <div className="work-meta">
                <span>📍 {inc.area}</span>
                <span>👥 {inc.people_affected}</span>
                <span className={`pill-alert-${inc.severity.toLowerCase()}`}>{inc.severity}</span>
                <span>{new Date(inc.created_at).toLocaleString()}</span>
              </div>
              {!missions && <ProgressNote status={inc.status} />}
              {missions && (
                <div className="action-button-group" style={{ marginTop: 10 }}>
                  {actionsFor(inc)
                    .filter((a) => a.kind === 'state' && a.to && FIELD_ACTIONS.has(a.to))
                    .map((a) => (
                      <button key={a.label} className="btn-primary btn-xs" onClick={() => move(inc, a.to as string)}>
                        {a.label}
                      </button>
                    ))}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
};

/** Plain-language status for people who reported an incident. */
const ProgressNote: React.FC<{ status: string }> = ({ status }) => {
  const text: Record<string, string> = {
    REPORTED: 'Received. The control room has not looked at it yet.',
    UNDER_VERIFICATION: 'The control room is checking your report.',
    VERIFIED: 'Confirmed. Waiting for a rescue team to be assigned.',
    QUEUED: 'Confirmed and in the queue for a rescue team.',
    TRIAGE_IN_PROGRESS: 'Being assessed by the supervisor system.',
    PENDING_APPROVAL: 'Waiting for a commander to approve dispatch.',
    DISPATCHED: 'A rescue team has been assigned.',
    IN_TRANSIT: 'A rescue team is on its way.',
    ON_SCENE: 'A rescue team is at the location.',
    RESOLVED: 'Resolved.',
    DUPLICATE: 'Merged with an earlier report of the same incident.',
    REJECTED: 'The control room could not act on this report. Call 112 if you still need help.',
    CANCELLED: 'Cancelled.',
  };
  return <p className="progress-note">{text[status] || humanStatus(status)}</p>;
};
