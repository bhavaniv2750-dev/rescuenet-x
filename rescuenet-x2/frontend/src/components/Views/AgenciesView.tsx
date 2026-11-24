import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { ApiError, api } from '../../api/client';
import type { AgencyRow, AuthUser, InvitationRow } from '../../api/types';
import { ROLE_LABEL } from '../../auth/access';
import { cleanMessage, toast } from '../../lib/toast';

const TYPE_LABEL: Record<string, string> = {
  DISASTER_RESPONSE: 'Disaster response', FIRE_EMERGENCY: 'Fire & emergency', MEDICAL_RESPONSE: 'Medical response',
  CIVIL_ADMINISTRATION: 'Civil administration', VOLUNTEER_ORGANIZATION: 'Volunteer organization',
};

/** Agencies are organisational labels for people and squads. They do NOT grant or limit access: permissions come from roles only.
 *  Invitations for staff roles are issued by a server operator; here an administrator can only see and revoke them. */
export const AgenciesView: React.FC = () => {
  const [tab, setTab] = useState<'agencies' | 'invitations'>('agencies');
  const [agencies, setAgencies] = useState<AgencyRow[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [invitations, setInvitations] = useState<InvitationRow[]>([]);
  const [teams, setTeams] = useState<{ id: string; name: string }[]>([]);
  const [teamAgency, setTeamAgency] = useState<Record<string, number>>({});
  const [note, setNote] = useState('');
  const [form, setForm] = useState({ name: '', agency_type: 'DISASTER_RESPONSE', region: '' });
  const [reauth, setReauth] = useState<{ retry: () => Promise<void> } | null>(null);
  const [code, setCode] = useState('');

  const load = useCallback(async () => {
    try {
      const a = await api.getAgencies();
      setAgencies(a.items); setTypes(a.types);
      setUsers((await api.getUsers()).items);
      setTeams((await api.getTeamOptions()).items);
      const map: Record<string, number> = {};
      await Promise.all(a.items.filter((x) => x.team_count > 0).map(async (x) => { (await api.getAgency(x.id)).teams?.forEach((t) => { map[t.id] = x.id; }); }));
      setTeamAgency(map);
      const inv = await api.getInvitations();
      setInvitations(inv.items); setNote(inv.note);
    } catch (e) {
      toast.error(cleanMessage(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  /** Sensitive actions need a recent authenticator code: ask for it, then retry the action once. */
  const guarded = async (action: () => Promise<unknown>, ok: string) => {
    const run = async () => {
      try {
        await action();
        toast.success(ok);
        load();
      } catch (e) {
        if (e instanceof ApiError && e.reauth) setReauth({ retry: run });
        else toast.error(cleanMessage(e));
      }
    };
    await run();
  };
  const submitReauth = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.mfaReauth(code.replace(/\s/g, ''));
      const again = reauth?.retry;
      setReauth(null); setCode('');
      if (again) await again();
    } catch (err) {
      toast.error(cleanMessage(err));
    }
  };

  return (
    <div className="admin-console">
      <div className="view-header">
        <div>
          <h1>Agencies &amp; invitations</h1>
          <p className="muted">Agencies are labels for the organisation people and squads belong to. They do not grant or limit access.</p>
        </div>
        <button className="btn-secondary" onClick={load}><RefreshCw size={14} /> Refresh</button>
      </div>
      <div className="seg-control seg-wide" role="tablist" style={{ maxWidth: 420 }}>
        <button role="tab" aria-selected={tab === 'agencies'} className={tab === 'agencies' ? 'seg-active' : ''} onClick={() => setTab('agencies')}>Agencies ({agencies.length})</button>
        <button role="tab" aria-selected={tab === 'invitations'} className={tab === 'invitations' ? 'seg-active' : ''} onClick={() => setTab('invitations')}>Invitations ({invitations.length})</button>
      </div>

      {reauth && (
        <form onSubmit={submitReauth} className="panel" style={{ padding: 16, display: 'grid', gap: 8 }} role="dialog" aria-label="Confirm with your authenticator code">
          <strong>Confirm with your authenticator code to continue</strong>
          <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={7} placeholder="6-digit code" autoComplete="one-time-code" />
          <button className="btn-primary" disabled={code.trim().length < 6}>Confirm</button>
          <button type="button" className="link-btn" onClick={() => setReauth(null)}>Cancel</button>
        </form>
      )}

      {tab === 'agencies' && (
        <>
          <form className="panel" style={{ padding: 16, display: 'grid', gap: 8 }} onSubmit={(e) => { e.preventDefault(); guarded(() => api.createAgency({ name: form.name.trim(), agency_type: form.agency_type, region: form.region.trim() || undefined }), 'Agency created.').then(() => setForm({ ...form, name: '', region: '' })); }}>
            <strong>Add an agency</strong>
            <div className="form-row">
              <label>Name<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required minLength={2} /></label>
              <label>Type
                <select value={form.agency_type} onChange={(e) => setForm({ ...form, agency_type: e.target.value })}>
                  {types.map((t) => <option key={t} value={t}>{TYPE_LABEL[t] || t}</option>)}
                </select>
              </label>
              <label>Region<input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} /></label>
              <button className="btn-primary" disabled={form.name.trim().length < 2}>Add</button>
            </div>
          </form>
          <section className="panel">
            <table className="data-table">
              <thead><tr><th>Name</th><th>Type</th><th>Region</th><th>People</th><th>Squads</th><th>Status</th><th /></tr></thead>
              <tbody>
                {agencies.length === 0 && <tr><td colSpan={7} className="muted">No agencies yet.</td></tr>}
                {agencies.map((a) => (
                  <tr key={a.id}>
                    <td>{a.name}</td><td>{TYPE_LABEL[a.agency_type] || a.agency_type}</td><td>{a.region || '—'}</td>
                    <td>{a.personnel_count}</td><td>{a.team_count}</td><td>{a.is_active ? 'Active' : 'Inactive'}</td>
                    <td><button className="btn-secondary" onClick={() => guarded(() => api.updateAgency(a.id, { is_active: !a.is_active }), a.is_active ? 'Agency deactivated.' : 'Agency activated.')}>{a.is_active ? 'Deactivate' : 'Activate'}</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="panel">
            <strong style={{ padding: 16, display: 'block' }}>Assign people</strong>
            <table className="data-table">
              <thead><tr><th>Person</th><th>Role</th><th>Agency</th></tr></thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.full_name} <span className="muted">({u.username})</span></td><td>{ROLE_LABEL[u.role]}</td>
                    <td>
                      <select aria-label={`Agency of ${u.username}`} value={u.agency_id ?? ''} onChange={(e) => guarded(() => api.setMemberAgency(u.id, e.target.value ? Number(e.target.value) : null), 'Saved.')}>
                        <option value="">— none —</option>
                        {agencies.filter((a) => a.is_active || a.id === u.agency_id).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          {teams.length > 0 && (
            <section className="panel">
              <strong style={{ padding: 16, display: 'block' }}>Associate squads</strong>
              <table className="data-table">
                <thead><tr><th>Squad</th><th>Agency</th></tr></thead>
                <tbody>
                  {teams.map((t) => (
                    <tr key={t.id}>
                      <td>{t.name}</td>
                      <td>
                        <select aria-label={`Agency of ${t.name}`} key={`${t.id}-${teamAgency[t.id] ?? ''}`} defaultValue={teamAgency[t.id] ?? ''} onChange={(e) => guarded(() => api.setTeamAgency(t.id, e.target.value ? Number(e.target.value) : null), 'Saved.')}>
                          <option value="">— none —</option>
                          {agencies.filter((a) => a.is_active).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}

      {tab === 'invitations' && (
        <section className="panel">
          <p className="muted" style={{ padding: 16, margin: 0 }}>{note} Run <code>python scripts/account_admin.py invite --help</code> on the server.</p>
          <table className="data-table">
            <thead><tr><th>Role</th><th>Recipient</th><th>Agency</th><th>Status</th><th>Expires</th><th /></tr></thead>
            <tbody>
              {invitations.length === 0 && <tr><td colSpan={6} className="muted">No invitations.</td></tr>}
              {invitations.map((i) => (
                <tr key={i.id}>
                  <td>{ROLE_LABEL[i.role]}</td><td data-sensitive>{i.recipient}</td><td>{i.agency || '—'}</td><td>{i.status}</td>
                  <td>{new Date(i.expires_at).toLocaleString()}</td>
                  <td>{i.status === 'PENDING' && <button className="btn-secondary" onClick={() => guarded(() => api.revokeInvitation(i.id), 'Invitation revoked.')}>Revoke</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
};
