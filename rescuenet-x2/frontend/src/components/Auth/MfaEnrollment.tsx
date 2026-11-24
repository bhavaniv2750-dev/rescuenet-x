import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { MfaEnrollStart } from '../../api/types';
import { cleanMessage } from '../../lib/toast';

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

  return (
    <div className={mandatory ? 'login-panel' : undefined}>
      <div className={mandatory ? 'login-card' : 'panel'} role="region" aria-label="Set up two-step sign-in">
        {mandatory && step !== 'codes' && (
          <div className="form-notice form-notice-info" role="status">
            Two-step sign-in is required for your role. Until it is set up, nothing else in RescueNet X is available to this account.
          </div>
        )}
        <h2>{step === 'codes' ? 'Save your recovery codes' : 'Set up two-step sign-in'}</h2>

        {step === 'password' && (
          <form onSubmit={start} className="login-form">
            <p className="login-sub">You need an authenticator app (for example Google Authenticator, Microsoft Authenticator, Aegis or 1Password). Confirm your password to begin.</p>
            <label htmlFor="mfa-pw">Current password</label>
            <input id="mfa-pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            {error && <div className="form-notice form-notice-error" role="alert">{error}</div>}
            <button className="btn-primary btn-block" disabled={busy || !password}>{busy ? 'Starting…' : 'Continue'}</button>
            {onCancel && <button type="button" className="link-btn" onClick={onCancel}>Cancel</button>}
          </form>
        )}

        {step === 'scan' && setup && (
          <form onSubmit={confirm} className="login-form">
            <ol className="text-sm">
              <li>Open your authenticator app and add an account by scanning this QR code.</li>
              <li>No camera? Choose "enter a setup key" and type the key below instead.</li>
              <li>Type the 6-digit code the app shows to finish.</li>
            </ol>
            <img data-sensitive src={setup.qr_svg_data_uri} alt="QR code to add RescueNet X to your authenticator app" width={190} height={190} style={{ background: '#fff', padding: 8, borderRadius: 8 }} />
            <div>
              <span className="text-xs text-muted">Setup key (shown only now)</span>
              <div data-sensitive className="font-mono" style={{ fontSize: 16, letterSpacing: 1, userSelect: 'all' }} aria-label="Setup key">{group(setup.secret)}</div>
              <span className="text-xs text-muted">Account: {setup.account} · Issuer: {setup.issuer} · 6 digits, 30 seconds</span>
            </div>
            <label htmlFor="mfa-confirm">6-digit code from the app</label>
            <input id="mfa-confirm" value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={8} required />
            {error && <div className="form-notice form-notice-error" role="alert">{error}</div>}
            <button className="btn-primary btn-block" disabled={busy || code.replace(/\s/g, '').length < 6}>{busy ? 'Checking…' : 'Turn on two-step sign-in'}</button>
          </form>
        )}

        {step === 'codes' && (
          <div className="login-form">
            <div className="form-notice form-notice-success" role="status">Two-step sign-in is now ON.</div>
            <p className="login-sub">
              If you lose your phone, each of these codes lets you sign in <strong>once</strong>. Store them offline, apart from your phone: print them or keep them in a
              password manager. They are shown only now. Generating a new set later cancels these.
            </p>
            <ul data-sensitive className="font-mono" style={{ columns: 2, listStyle: 'none', padding: 0, fontSize: 15 }} aria-label="Recovery codes">
              {codes.map((c) => <li key={c}>{c}</li>)}
            </ul>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button type="button" className="btn-secondary" onClick={() => navigator.clipboard?.writeText(codes.join('\n'))}>Copy</button>
              <button type="button" className="btn-secondary" onClick={download}>Download as a text file</button>
              <button type="button" className="btn-secondary" onClick={() => window.print()}>Print</button>
            </div>
            <label className="check-row">
              <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
              I have stored my recovery codes somewhere safe
            </label>
            <button className="btn-primary btn-block" disabled={!saved} onClick={onDone}>Continue</button>
          </div>
        )}
      </div>
    </div>
  );
};
