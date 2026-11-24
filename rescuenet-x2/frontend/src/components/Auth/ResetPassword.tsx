import { useState } from 'react';
import { api } from '../../api/client';
import { cleanMessage } from '../../lib/toast';
import { Button, TextField } from '../ui';
import { AuthHeading, AuthLayout } from './AuthLayout';

/** Opened from the emailed link (?reset=TOKEN). The token is read once and removed from the address bar. */
export const ResetPassword: React.FC<{ token: string; onDone: () => void }> = ({ token, onDone }) => {
  const [pw, setPw] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { setDone((await api.resetPassword(token, pw)).message); }
    catch (err) { setError(cleanMessage(err)); }
    finally { setBusy(false); }
  };

  return (
    <AuthLayout>
      <AuthHeading title="Choose a new password" />
      {done ? (
        <>
          <div className="auth-notice auth-notice-ok" role="status">{done}</div>
          <Button variant="primary" block onClick={onDone}>Go to sign in</Button>
        </>
      ) : (
        <form onSubmit={submit} className="auth-form">
          <TextField label="New password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" required hint="At least 8 characters, mixing letters with numbers or symbols." />
          <TextField label="Repeat new password" type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required
            error={again && pw !== again ? 'The two passwords do not match.' : null} />
          {error && <div className="auth-notice auth-notice-error" role="alert">{error}</div>}
          <Button type="submit" variant="primary" block loading={busy} disabled={!pw || pw !== again}>Set new password</Button>
          <button type="button" className="link-btn" onClick={onDone}>Cancel</button>
        </form>
      )}
    </AuthLayout>
  );
};
