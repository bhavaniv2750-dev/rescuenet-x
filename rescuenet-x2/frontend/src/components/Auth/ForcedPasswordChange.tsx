import { useState } from 'react';
import { api } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { cleanMessage } from '../../lib/toast';

/** Shown instead of the app while the account still has a temporary password (host-level recovery or an administrator's
 *  reset). The server refuses every other request until the owner chooses a new password. */
export const ForcedPasswordChange: React.FC = () => {
  const { user, logout, refreshUser } = useAuth();
  const [current, setCurrent] = useState('');
  const [pw, setPw] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.changePassword(current, pw);
      await refreshUser();
    } catch (err) {
      setError(cleanMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-panel">
      <div className="login-card">
        <h2>Choose your own password</h2>
        <p className="login-sub">
          {user?.full_name}, you signed in with a temporary password. Until you choose a new one, nothing else in RescueNet X is available to this
          account. The new password must be different from the temporary one.
        </p>
        <form onSubmit={submit} className="login-form">
          <label>
            Temporary password
            <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
          </label>
          <label>
            New password
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" required />
          </label>
          <label>
            Repeat new password
            <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
            {again && pw !== again && <span className="field-error">The two passwords do not match.</span>}
          </label>
          {error && <div className="form-notice form-notice-error" role="alert">{error}</div>}
          <button className="btn-primary btn-block" disabled={busy || !current || !pw || pw !== again}>{busy ? 'Saving…' : 'Set my password'}</button>
          <button type="button" className="link-btn" onClick={logout}>Sign out</button>
        </form>
      </div>
    </div>
  );
};
