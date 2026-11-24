import { useEffect, useRef, useState } from 'react';
import { cleanMessage } from '../../lib/toast';
import { Button } from '../ui';
import { AuthHeading } from './AuthLayout';

interface Props {
  /** Resolves on success, throws on a wrong/expired code. */
  onSubmit: (input: { code?: string; recovery_code?: string }) => Promise<unknown>;
  onCancel: () => void;
  expiresInSeconds: number;
}

/** Second step of sign-in. Shown only after the password was accepted for an account with MFA: no session exists yet. */
export const MfaChallenge: React.FC<Props> = ({ onSubmit, onCancel, expiresInSeconds }) => {
  const [useRecovery, setUseRecovery] = useState(false);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.focus(), [useRecovery]);
  useEffect(() => {
    const t = window.setTimeout(() => setExpired(true), expiresInSeconds * 1000);
    return () => window.clearTimeout(t);
  }, [expiresInSeconds]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await onSubmit(useRecovery ? { recovery_code: value.trim() } : { code: value.replace(/\s/g, '') }); }
    catch (err) { setError(cleanMessage(err)); setValue(''); }
    finally { setBusy(false); }
  };

  if (expired) {
    return (
      <div role="alert" className="auth-form">
        <AuthHeading title="Sign-in expired" sub="Too much time passed after your password. Please sign in again." />
        <Button variant="primary" block onClick={onCancel}>Back to sign in</Button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="auth-form" aria-labelledby="mfa-title">
      <AuthHeading id="mfa-title" title={useRecovery ? 'Enter a recovery code' : 'Enter your authenticator code'}
        sub={useRecovery ? 'Use one of the recovery codes you saved when you set up two-step sign-in. Each code works once.' : 'Open your authenticator app and type the 6-digit code for RescueNet X.'} />
      <div className="rn-field">
        <label htmlFor="mfa-input">{useRecovery ? 'Recovery code' : '6-digit code'}</label>
        <input id="mfa-input" ref={input} className="rn-input auth-mono" value={value} onChange={(e) => setValue(e.target.value)}
          inputMode={useRecovery ? 'text' : 'numeric'} autoComplete="one-time-code" maxLength={useRecovery ? 24 : 8} aria-describedby={error ? 'mfa-error' : undefined} required />
      </div>
      {error && <div id="mfa-error" className="auth-notice auth-notice-error" role="alert">{error}</div>}
      <Button type="submit" variant="primary" block loading={busy} disabled={value.trim().length < 6}>Verify and sign in</Button>
      <button type="button" className="link-btn" onClick={() => { setUseRecovery((v) => !v); setValue(''); setError(null); }}>
        {useRecovery ? 'Use my authenticator app instead' : 'I cannot use my authenticator: use a recovery code'}
      </button>
      <button type="button" className="link-btn" onClick={onCancel}>Cancel</button>
    </form>
  );
};
