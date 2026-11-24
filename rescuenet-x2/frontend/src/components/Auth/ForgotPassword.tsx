import { useState } from 'react';
import { api } from '../../api/client';
import { cleanMessage } from '../../lib/toast';
import { Button, TextField } from '../ui';
import { AuthHeading } from './AuthLayout';
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
    setBusy(true); setError(null);
    try { setAnswer((await api.forgotPassword(identifier.trim())).message); setTick((t) => t + 1); }
    catch (err) { setError(cleanMessage(err)); }
    finally { setBusy(false); }
  };

  return (
    <>
      <AuthHeading title="Reset your password" sub="Enter your username or email address. A reset link is requested only for accounts whose email address has been verified." />
      <form onSubmit={submit} className="auth-form">
        <TextField label="Username or email" value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" required />
        {error && <div className="auth-notice auth-notice-error" role="alert">{error}</div>}
        {answer && <div className="auth-notice auth-notice-info" role="status">{answer}</div>}
        <Button type="submit" variant="primary" block loading={busy} disabled={!identifier.trim()}>Request reset link</Button>
        <button type="button" className="link-btn" onClick={onBack}>Back to sign in</button>
      </form>
      <p className="rn-field-hint">Staff accounts that cannot recover by email should contact the person who runs this server.</p>
      <DevOutbox refreshKey={tick} />
    </>
  );
};
