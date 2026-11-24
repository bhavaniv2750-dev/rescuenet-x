import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { Capabilities } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { cleanMessage } from '../../lib/toast';

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
    <div className="login-panel">
      <div className="login-card">
        <h2>Verify your email address</h2>
        <p className="login-sub">
          {user?.full_name}, before this account can be used we need to confirm that you control <span data-sensitive>{user?.email || 'an email address'}</span>.
          Nothing else in RescueNet X is available until then.
        </p>
        {unavailable && (
          <div className="form-notice form-notice-error" role="alert">
            This server cannot send email right now, so a code cannot be delivered. Ask your server operator to configure email or to
            record a waiver for your account.
          </div>
        )}
        {devOutbox && <div className="form-notice" role="note">Development server: codes are held in the development outbox, not delivered to any mailbox.</div>}
        {!user?.email && <div className="form-notice form-notice-error" role="alert">This account has no email address on file. Ask your server operator for help.</div>}
        <form onSubmit={confirm} className="login-form">
          <button type="button" className="btn-secondary btn-block" onClick={send} disabled={busy || unavailable || !user?.email}>Send me a code</button>
          {note && <div className="form-notice form-notice-success" role="status">{note}</div>}
          <label>
            Six-digit code
            <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={6} />
          </label>
          {error && <div className="form-notice form-notice-error" role="alert">{error}</div>}
          <button className="btn-primary btn-block" disabled={busy || code.trim().length < 4}>Verify</button>
          <button type="button" className="link-btn" onClick={logout}>Sign out</button>
        </form>
      </div>
    </div>
  );
};
