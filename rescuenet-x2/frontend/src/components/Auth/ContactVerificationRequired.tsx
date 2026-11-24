import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { Capabilities } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { cleanMessage } from '../../lib/toast';
import { Button } from '../ui';
import { AuthHeading, AuthLayout } from './AuthLayout';

/** Shown instead of the app while the account must prove control of its email address (invited accounts, and privileged
 *  accounts under the production policy). It states plainly when email cannot be delivered: it never pretends. */
export const ContactVerificationRequired: React.FC = () => {
  const { user, logout, refreshUser } = useAuth();
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [code, setCode] = useState('');
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.getCapabilities().then(setCaps).catch(() => undefined);
  }, []);

  const send = async () => {
    setBusy(true); setError(null);
    try {
      setNote((await api.requestVerification('email')).message);
    } catch (err) {
      setError(cleanMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const confirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api.confirmVerification('email', code.trim());
      await refreshUser();
    } catch (err) {
      setError(cleanMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const unavailable = caps?.email_delivery.transport === 'DISABLED';
  const devOutbox = caps?.email_delivery.transport === 'DEV_OUTBOX';
  return (
    <AuthLayout>
      <AuthHeading title="Verify your email address" sub={<>{user?.full_name}, before this account can be used we need to confirm that you control <span data-sensitive>{user?.email || 'an email address'}</span>. Nothing else in RescueNet X is available until then.</>} />
      {unavailable && (
        <div className="auth-notice auth-notice-error" role="alert">
          This server cannot send email right now, so a code cannot be delivered. Ask your server operator to configure email or to record a waiver for your account.
        </div>
      )}
      {devOutbox && <div className="auth-notice auth-notice-info" role="note">Development server: codes are held in the development outbox, not delivered to any mailbox.</div>}
      {!user?.email && <div className="auth-notice auth-notice-error" role="alert">This account has no email address on file. Ask your server operator for help.</div>}
      <form onSubmit={confirm} className="auth-form">
        <Button block onClick={send} disabled={busy || unavailable || !user?.email}>Send me a code</Button>
        {note && <div className="auth-notice auth-notice-ok" role="status">{note}</div>}
        <div className="rn-field">
          <label htmlFor="verify-code">Six-digit code</label>
          <input id="verify-code" className="rn-input auth-mono" value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={6} />
        </div>
        {error && <div className="auth-notice auth-notice-error" role="alert">{error}</div>}
        <Button type="submit" variant="primary" block loading={busy} disabled={code.trim().length < 4}>Verify</Button>
        <button type="button" className="link-btn" onClick={logout}>Sign out</button>
      </form>
    </AuthLayout>
  );
};
