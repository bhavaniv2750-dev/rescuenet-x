import { useState } from 'react';
import { api } from '../../api/client';
import { cleanMessage } from '../../lib/toast';

/** Opened from the emailed link (?reset=TOKEN). The token is read once and removed from the address bar. */
export const ResetPassword: React.FC<{ token: string; onDone: () => void }> = ({ token, onDone }) => {
  const [pw, setPw] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setDone((await api.resetPassword(token, pw)).message);
    } catch (err) {
      setError(cleanMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-panel">
      <div className="login-card">
        <h2>Choose a new password</h2>
        {done ? (
          <>
            <div className="form-notice form-notice-success" role="status">{done}</div>
            <button className="btn-primary btn-block" onClick={onDone}>Go to sign in</button>
          </>
        ) : (
          <form onSubmit={submit} className="login-form">
            <label>
              New password
              <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" required />
              <span className="field-help">At least 8 characters, mixing letters with numbers or symbols.</span>
            </label>
            <label>
              Repeat new password
              <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
              {again && pw !== again && <span className="field-error">The two passwords do not match.</span>}
            </label>
            {error && <div className="form-notice form-notice-error" role="alert">{error}</div>}
            <button className="btn-primary btn-block" disabled={busy || !pw || pw !== again}>{busy ? 'Saving…' : 'Set new password'}</button>
            <button type="button" className="link-btn" onClick={onDone}>Cancel</button>
          </form>
        )}
      </div>
    </div>
  );
};
