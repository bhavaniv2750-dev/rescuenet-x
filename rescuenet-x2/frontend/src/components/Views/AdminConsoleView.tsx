import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, UserPlus } from 'lucide-react';
import { api } from '../../api/client';
import type { AuditEntry, AuthUser, RescueTeam, Role } from '../../api/types';
import { ROLE_LABEL } from '../../auth/access';
import { useAuth } from '../../auth/AuthContext';
import { cleanMessage, toast } from '../../lib/toast';

const STAFF_ROLES: Role[] = ['ADMIN', 'DEVELOPER', 'COMMANDER', 'OPERATOR', 'RESCUE_OFFICER'];

interface Props {
  /** Commanders get the audit log only. Administrators also manage accounts. */
  canManageUsers: boolean;
  teams: RescueTeam[];
}

export const AdminConsoleView: React.FC<Props> = ({ canManageUsers, teams }) => {
  const { user: me } = useAuth();
  const [tab, setTab] = useState<'users' | 'audit' | 'system'>(canManageUsers ? 'users' : 'audit');
  const [diag, setDiag] = useState<Record<string, any> | null>(null);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [filter, setFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('ALL');
  const [showCreate, setShowCreate] = useState(false);
  const [teamOptions, setTeamOptions] = useState<{ id: string; name: string }[]>([]);

  const load = useCallback(async () => {
    try {
      if (canManageUsers) {
        setTeamOptions((await api.getTeamOptions()).items);
        setUsers((await api.getUsers()).items);
        setDiag(await api.getDiagnostics());
      }
      const a = await api.getAuditLog(200, filter || undefined);
      setAudit(a.items);
      setAuditTotal(a.count);
    } catch (e) {
      toast.error(cleanMessage(e));
    }
  }, [canManageUsers, filter]);

  useEffect(() => {
    load();
  }, [load]);

  const patch = async (u: AuthUser, body: Record<string, unknown>, ok: string) => {
    try {
      await api.updateUser(u.id, body);
      toast.success(ok);
      load();
    } catch (e) {
      toast.error(cleanMessage(e));
    }
  };

  const resetPassword = (u: AuthUser) => {
    const pw = window.prompt(`New password for ${u.username} (min 8 characters, letters and numbers):`);
    if (pw) patch(u, { new_password: pw }, `Password reset for ${u.username}.`);
  };

  const shown = users.filter((u) => roleFilter === 'ALL' || u.role === roleFilter);
  const actions = Array.from(new Set(audit.map((a) => a.action))).sort();

  return (
    <div className="admin-console">
      <div className="view-header">
        <div>
          <h2>{canManageUsers ? 'Admin Console' : 'Audit Log'}</h2>
          <p>{canManageUsers ? 'Manage accounts and review who did what.' : 'Who did what, and when.'}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-secondary" onClick={load}>
            <RefreshCw size={14} /> Refresh
          </button>
          {canManageUsers && tab === 'users' && (
            <button className="btn-primary" onClick={() => setShowCreate(true)}>
              <UserPlus size={14} /> New staff account
            </button>
          )}
        </div>
      </div>

      {canManageUsers && (
        <div className="seg-control seg-wide" role="tablist" style={{ maxWidth: 560 }}>
          <button role="tab" aria-selected={tab === 'users'} className={tab === 'users' ? 'seg-active' : ''} onClick={() => setTab('users')}>
            Accounts ({users.length})
          </button>
          <button role="tab" aria-selected={tab === 'audit'} className={tab === 'audit' ? 'seg-active' : ''} onClick={() => setTab('audit')}>
            Audit log ({auditTotal})
          </button>
          <button role="tab" aria-selected={tab === 'system'} className={tab === 'system' ? 'seg-active' : ''} onClick={() => setTab('system')}>
            System{diag?.warnings?.length ? ` (${diag.warnings.length})` : ''}
          </button>
        </div>
      )}

      {tab === 'users' && canManageUsers && (
        <section className="panel">
          <div className="filter-bar">
            <div className="filter-group">
              <span>Role:</span>
              {['ALL', ...Object.keys(ROLE_LABEL)].map((r) => (
                <button key={r} className={`filter-btn ${roleFilter === r ? 'active' : ''}`} onClick={() => setRoleFilter(r)}>
                  {r === 'ALL' ? 'All' : ROLE_LABEL[r as Role]}
                </button>
              ))}
            </div>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>NAME</th>
                  <th>USERNAME</th>
                  <th>ROLE</th>
                  <th>TEAM / VOLUNTEER</th>
                  <th>STATUS</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((u) => (
                  <tr key={u.id} className={u.is_active ? '' : 'row-resolved'}>
                    <td>
                      <strong>{u.full_name}</strong>
                      <div className="text-muted text-xs">{u.email || u.phone || ''}</div>
                    </td>
                    <td className="font-mono">{u.username}</td>
                    <td>{ROLE_LABEL[u.role]}</td>
                    <td className="font-mono text-xs">{u.team_id || u.volunteer_id || '—'}</td>
                    <td>
                      <span className={`status-pill ${u.is_active ? 'pill-active' : 'pill-muted'}`}>{u.is_active ? 'ACTIVE' : 'DISABLED'}</span>
                    </td>
                    <td>
                      <div className="action-button-group">
                        <button className="btn-secondary btn-xs" onClick={() => resetPassword(u)}>
                          Reset password
                        </button>
                        <button
                          className="btn-secondary btn-xs"
                          disabled={u.id === me?.id}
                          title={u.id === me?.id ? 'You cannot disable your own account' : ''}
                          onClick={() => patch(u, { is_active: !u.is_active }, `${u.username} ${u.is_active ? 'disabled' : 'enabled'}.`)}
                        >
                          {u.is_active ? 'Disable' : 'Enable'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === 'audit' && (
        <section className="panel">
          <div className="filter-bar">
            <div className="filter-group">
              <span>Action:</span>
              <select className="select-input" value={filter} onChange={(e) => setFilter(e.target.value)}>
                <option value="">All actions</option>
                {Array.from(new Set([...actions, filter].filter(Boolean))).map((a) => (
                  <option key={a} value={a}>
                    {a.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
              <span className="text-muted text-xs">Showing the latest {audit.length} of {auditTotal}</span>
            </div>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>WHEN</th>
                  <th>WHO</th>
                  <th>ACTION</th>
                  <th>TARGET</th>
                  <th>DETAILS</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.id}>
                    <td className="font-mono text-xs">{new Date(String(a.created_at) + (String(a.created_at).endsWith('Z') ? '' : 'Z')).toLocaleString()}</td>
                    <td>
                      {a.actor}
                      <div className="text-muted text-xs">{a.role}</div>
                    </td>
                    <td>{a.action.replace(/_/g, ' ')}</td>
                    <td className="font-mono text-xs">
                      {a.target_type} {a.target_id}
                    </td>
                    <td className="text-xs text-muted">{a.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === 'system' && canManageUsers && diag && (
        <div className="two-col">
          <section className="panel">
            <div className="panel-title-bar"><h3>Needs attention ({diag.warnings.length})</h3></div>
            {diag.warnings.length === 0 ? (
              <div className="empty-state"><strong>Nothing to fix</strong></div>
            ) : (
              <ul className="plain-list">
                {diag.warnings.map((w: string) => (
                  <li key={w} style={{ fontSize: 13, lineHeight: 1.45 }}>{w}</li>
                ))}
              </ul>
            )}
          </section>
          <section className="panel">
            <div className="panel-title-bar"><h3>Status</h3></div>
            <div className="kv-list">
              {[
                ['Python', diag.runtime.python],
                ['Flood model', diag.flood_model.loaded ? `loaded, CV accuracy ${((diag.flood_model.cv_accuracy ?? 0) * 100).toFixed(1)}%` : 'not loaded'],
                ['Photo models', diag.vision_model.ready ? 'installed' : 'not installed'],
                ['Ollama', diag.ollama.available ? `online (${diag.ollama.model})` : 'offline, fallback in use'],
                ['Accounts', String(diag.database.tables.users)],
                ['Incidents', `${diag.database.tables.incidents} (${Object.entries(diag.database.incidents_by_data_label).map(([k, v]) => `${v} ${String(k).toLowerCase()}`).join(', ')})`],
                ['Audit entries', String(diag.database.tables.audit_entries)],
                ['Uploads', `${diag.storage.uploads_mb} MB`],
                ['Demo mode', diag.auth.demo_mode ? 'on' : 'off'],
              ].map(([k, v]) => (
                <div key={k} className="kv-row"><span>{k}</span><strong>{v}</strong></div>
              ))}
            </div>
          </section>
        </div>
      )}

      {showCreate && <CreateUserModal teams={teamOptions.length ? teamOptions : teams} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
    </div>
  );
};

const CreateUserModal: React.FC<{ teams: { id: string; name: string }[]; onClose: () => void; onCreated: () => void }> = ({ teams, onClose, onCreated }) => {
  const [role, setRole] = useState<Role>('OPERATOR');
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [teamId, setTeamId] = useState(teams[0]?.id || '');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createUser({
        role,
        username: username.trim().toLowerCase(),
        full_name: fullName.trim(),
        password,
        team_id: role === 'RESCUE_OFFICER' ? teamId : undefined,
      });
      toast.success(`Account ${username} created.`);
      onCreated();
    } catch (err) {
      toast.error(cleanMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-box" style={{ maxWidth: 460 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>New staff account</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <form onSubmit={submit} className="login-form" style={{ padding: 16 }}>
          <label>
            Role
            <select className="select-input" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {STAFF_ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Full name
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </label>
          <label>
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoCapitalize="none" required />
          </label>
          <label>
            Temporary password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required />
            <span className="field-help">At least 8 characters, mixing letters with numbers or symbols. Ask them to change it at first sign-in.</span>
          </label>
          {role === 'RESCUE_OFFICER' && (
            <label>
              Team
              <select className="select-input" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button className="btn-primary" disabled={busy || !username || !fullName || !password}>
              {busy ? 'Creating…' : 'Create account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
