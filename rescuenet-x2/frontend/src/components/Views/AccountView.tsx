import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { ROLE_LABEL } from '../../auth/access';
import type { SessionInfo } from '../../api/types';
import { cleanMessage, toast } from '../../lib/toast';

export const AccountView: React.FC = () => {
  const { user, logout } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);

  const loadSessions = useCallback(() => {
    api.getSessions().then((r) => setSessions(r.items)).catch(() => undefined);
  }, []);
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  if (!user) return null;

  const mismatch = again.length > 0 && next !== again;

  const change = async (e: React.FormEvent) => {
    e.preventDefault();
    if (next !== again) return;
    setBusy(true);
    try {
      await api.changePassword(current, next);
      toast.success('Password changed. Other devices were signed out.');
      loadSessions();
      setCurrent('');
      setNext('');
      setAgain('');
    } catch (err) {
      toast.error(cleanMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const row = (label: string, value?: string | null) => (
    <div className="kv-row">
      <span>{label}</span>
      <strong>{value || '—'}</strong>
    </div>
  );

  return (
    <div className="account-view">
      <div className="view-header">
        <div>
          <h2>My Account</h2>
          <p>Your profile and sign-in settings.</p>
        </div>
        <button className="btn-secondary" onClick={logout}>
          Sign out
        </button>
      </div>

      <div className="two-col">
        <section className="panel">
          <div className="panel-title-bar">
            <h3>Profile</h3>
          </div>
          <div className="kv-list">
            {row('Name', user.full_name)}
            {row('Username', user.username)}
            {row('Role', ROLE_LABEL[user.role])}
            {row('Email', user.email)}
            {row('Phone', user.phone)}
            {user.team_id && row('Team', user.team_id)}
            {user.volunteer_id && row('Volunteer ID', user.volunteer_id)}
          </div>
          {user.role === 'VOLUNTEER' && (
            <div className={`form-notice ${user.volunteer_verified ? 'form-notice-success' : 'form-notice-info'}`} style={{ marginTop: 12 }}>
              {user.volunteer_verified
                ? 'You are a verified volunteer and can be assigned to rescues.'
                : 'Waiting for a coordinator to verify you. You can be assigned to rescues after that.'}
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-title-bar">
            <h3>Change password</h3>
          </div>
          <form onSubmit={change} className="login-form">
            <label>
              Current password
              <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
            </label>
            <label>
              New password
              <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required />
              <span className="field-help">At least 8 characters, mixing letters with numbers or symbols.</span>
            </label>
            <label>
              Repeat new password
              <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
              {mismatch && <span className="field-error">The two passwords do not match.</span>}
            </label>
            <button className="btn-primary" disabled={busy || !current || !next || next !== again}>
              {busy ? 'Saving…' : 'Change password'}
            </button>
          </form>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title-bar">
          <div>
            <h3>Where you are signed in</h3>
            <p>Sign out of any device you do not recognise. Changing your password signs out every other device.</p>
          </div>
          <button
            className="btn-secondary"
            onClick={() => api.logoutAll().then(() => logout()).catch((e) => toast.error(cleanMessage(e)))}
          >
            Sign out everywhere
          </button>
        </div>
        <table className="data-table">
          <thead>
            <tr><th>Device</th><th>Signed in</th><th>Last active</th><th>Ends</th><th /></tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id}>
                <td>{s.user_agent ? s.user_agent.slice(0, 60) : 'Unknown device'} {s.current && <strong>(this device)</strong>}</td>
                <td>{new Date(s.created_at + 'Z').toLocaleString()}</td>
                <td>{new Date(s.last_used_at + 'Z').toLocaleString()}</td>
                <td>{new Date(s.expires_at + 'Z').toLocaleString()}</td>
                <td>
                  {!s.current && (
                    <button className="btn-secondary btn-xs" onClick={() => api.revokeSession(s.id).then(loadSessions).catch((e) => toast.error(cleanMessage(e)))}>
                      Sign out
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
};
