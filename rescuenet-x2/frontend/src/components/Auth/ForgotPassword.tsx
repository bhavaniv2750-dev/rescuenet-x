import { useState } from 'react';
import { api } from '../../api/client';
import { cleanMessage } from '../../lib/toast';
import { DevOutbox } from './DevOutbox';

/** Ask for a password-reset link. The answer is identical whether or not an account matches. */
export const ForgotPassword: React.FC<{ onBack: () => void }> = ({ onBack }) => {
  const [identifier, setIdentifier] = useState('');
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setAnswer((await api.forgotPassword(identifier.trim())).message);
      setTick((t) => t + 1);
    } catch (err) {
      setError(cleanMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h2>Reset your password</h2>
      <p className="login-sub">Enter your username or email address. A reset link is requested only for accounts whose email address has been verified.</p>
      <form onSubmit={submit} className="login-form">
        <label>
          Username or email
          <input value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" required />
        </label>
        {error && <div className="form-notice form-notice-error" role="alert">{error}</div>}
        {answer && <div className="form-notice form-notice-info" role="status">{answer}</div>}
        <button className="btn-primary btn-block" disabled={busy || !identifier.trim()}>{busy ? 'Requesting…' : 'Request reset link'}</button>
        <button type="button" className="link-btn" onClick={onBack}>Back to sign in</button>
      </form>
      <p className="text-xs text-muted" style={{ marginTop: 12 }}>
        Staff accounts that cannot recover by email should contact the person who runs this server.
      </p>
      <DevOutbox refreshKey={tick} />
    </div>
  );
};
