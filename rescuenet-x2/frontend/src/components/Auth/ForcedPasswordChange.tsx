import { useState } from 'react';
import { api } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { cleanMessage } from '../../lib/toast';
import { Button, TextField } from '../ui';
import { AuthHeading, AuthLayout } from './AuthLayout';

/** Shown instead of the app while the account still has a temporary password (host-level recovery or an administrator's reset).
 *  The server refuses every other request until the owner chooses a new password. */
export const ForcedPasswordChange: React.FC = () => {
  const { user, logout, refreshUser } = useAuth();
  const [current, setCurrent] = useState('');
  const [pw, setPw] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await api.changePassword(current, pw); await refreshUser(); }
    catch (err) { setError(cleanMessage(err)); }
    finally { setBusy(false); }
  };

  return (
    <AuthLayout>
      <AuthHeading title="Choose your own password" sub={<>{user?.full_name}, you signed in with a temporary password. Until you choose a new one, nothing else in RescueNet X is available to this account. The new password must differ from the temporary one.</>} />
      <form onSubmit={submit} className="auth-form">
        <TextField label="Temporary password" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        <TextField label="New password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" required hint="At least 8 characters, mixing letters with numbers or symbols." />
        <TextField label="Repeat new password" type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required error={again && pw !== again ? 'The two passwords do not match.' : null} />
        {error && <div className="auth-notice auth-notice-error" role="alert">{error}</div>}
        <Button type="submit" variant="primary" block loading={busy} disabled={!current || !pw || pw !== again}>Set my password</Button>
        <button type="button" className="link-btn" onClick={logout}>Sign out</button>
      </form>
    </AuthLayout>
  );
};
