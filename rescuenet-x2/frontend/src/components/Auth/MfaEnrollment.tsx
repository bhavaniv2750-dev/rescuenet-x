import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { MfaEnrollStart } from '../../api/types';
import { cleanMessage } from '../../lib/toast';
import { Button } from '../ui';
import { AuthHeading, AuthLayout } from './AuthLayout';

interface Props {
  /** Mandatory (staff, administrators, developers): nothing else in the app is available until this is finished. */
  mandatory?: boolean;
  /** Called after the user confirmed they stored their recovery codes. */
  onDone: () => void;
  onCancel?: () => void;
  userName?: string;
}

const group = (s: string) => s.replace(/(.{4})/g, '$1 ').trim();

/** Set up an authenticator app: password again -> QR code (or typed key) -> confirm with a code -> recovery codes (shown once).
 *  The secret and the codes live only in this component's memory: never in storage, never logged, never in the URL. */
export const MfaEnrollment: React.FC<Props> = ({ mandatory, onDone, onCancel, userName }) => {
  const [step, setStep] = useState<'password' | 'scan' | 'codes'>('password');
  const [password, setPassword] = useState('');
  const [setup, setSetup] = useState<MfaEnrollStart | null>(null);
  const [code, setCode] = useState('');
  const [codes, setCodes] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Forget the secret and codes when this screen goes away.
  useEffect(() => () => { setSetup(null); setCodes([]); }, []);

  const start = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { setSetup(await api.mfaEnrollStart(password)); setPassword(''); setStep('scan'); }
    catch (err) { setError(cleanMessage(err)); }
    finally { setBusy(false); }
  };

  const confirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { const r = await api.mfaEnrollConfirm(code.replace(/\s/g, '')); setCodes(r.recovery_codes); setSetup(null); setStep('codes'); }
    catch (err) { setError(cleanMessage(err)); setCode(''); }
    finally { setBusy(false); }
  };

  const download = () => {
    const blob = new Blob([`RescueNet X recovery codes for ${userName ?? 'your account'}\nEach code works once. Keep this file offline.\n\n${codes.join('\n')}\n`], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'rescuenet-recovery-codes.txt';
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const inner = (
    <div role="region" aria-label="Set up two-step sign-in" className="auth-form">
      {mandatory && step !== 'codes' && (
        <div className="auth-notice auth-notice-info" role="status">
          Two-step sign-in is required for your role. Until it is set up, nothing else in RescueNet X is available to this account.
        </div>
      )}
      <AuthHeading title={step === 'codes' ? 'Save your recovery codes' : 'Set up two-step sign-in'} />

      {step === 'password' && (
        <form onSubmit={start} className="auth-form">
          <p className="rn-field-hint">You need an authenticator app (for example Google Authenticator, Microsoft Authenticator, Aegis or 1Password). Confirm your password to begin.</p>
          <div className="rn-field">
            <label htmlFor="mfa-pw">Current password</label>
            <input id="mfa-pw" className="rn-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </div>
          {error && <div className="auth-notice auth-notice-error" role="alert">{error}</div>}
          <Button type="submit" variant="primary" block loading={busy} disabled={!password}>Continue</Button>
          {onCancel && <button type="button" className="link-btn" onClick={onCancel}>Cancel</button>}
        </form>
      )}

      {step === 'scan' && setup && (
        <form onSubmit={confirm} className="auth-form">
          <ol className="rn-field-hint" style={{ paddingLeft: 18, lineHeight: 1.6 }}>
            <li>Open your authenticator app and add an account by scanning this QR code.</li>
            <li>No camera? Choose "enter a setup key" and type the key below instead.</li>
            <li>Type the 6-digit code the app shows to finish.</li>
          </ol>
          <img data-sensitive className="auth-secret" src={setup.qr_svg_data_uri} alt="QR code to add RescueNet X to your authenticator app" width={190} height={190} />
          <div>
            <span className="rn-field-hint">Setup key (shown only now)</span>
            <div data-sensitive className="auth-mono" style={{ fontSize: 16, userSelect: 'all' }} aria-label="Setup key">{group(setup.secret)}</div>
            <span className="rn-field-hint">Account: {setup.account} · Issuer: {setup.issuer} · 6 digits, 30 seconds</span>
          </div>
          <div className="rn-field">
            <label htmlFor="mfa-confirm">6-digit code from the app</label>
            <input id="mfa-confirm" className="rn-input auth-mono" value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={8} required />
          </div>
          {error && <div className="auth-notice auth-notice-error" role="alert">{error}</div>}
          <Button type="submit" variant="primary" block loading={busy} disabled={code.replace(/\s/g, '').length < 6}>Turn on two-step sign-in</Button>
        </form>
      )}

      {step === 'codes' && (
        <div className="auth-form">
          <div className="auth-notice auth-notice-ok" role="status">Two-step sign-in is now ON.</div>
          <p className="rn-field-hint">
            If you lose your phone, each of these codes lets you sign in <strong>once</strong>. Store them offline, apart from your phone: print them or keep them in a
            password manager. They are shown only now. Generating a new set later cancels these.
          </p>
          <ul data-sensitive className="auth-codes" aria-label="Recovery codes">
            {codes.map((c) => <li key={c}>{c}</li>)}
          </ul>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Button onClick={() => navigator.clipboard?.writeText(codes.join('\n'))}>Copy</Button>
            <Button onClick={download}>Download as a text file</Button>
            <Button onClick={() => window.print()}>Print</Button>
          </div>
          <label className="auth-check">
            <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
            <span>I have stored my recovery codes somewhere safe</span>
          </label>
          <Button variant="primary" block disabled={!saved} onClick={onDone}>Continue</Button>
        </div>
      )}
    </div>
  );
  return mandatory ? <AuthLayout wide>{inner}</AuthLayout> : <div className="panel" style={{ padding: 16 }}>{inner}</div>;
};
