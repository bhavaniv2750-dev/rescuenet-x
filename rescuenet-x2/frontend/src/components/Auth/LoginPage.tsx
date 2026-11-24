import React, { useEffect, useState } from 'react';
import { Eye, EyeOff, Siren } from 'lucide-react';
import { api } from '../../api/client';
import type { PortalInfo } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { cleanMessage } from '../../lib/toast';
import { Button, TextField } from '../ui';
import { AuthHeading, AuthLayout } from './AuthLayout';
import { ForgotPassword } from './ForgotPassword';
import { MfaChallenge } from './MfaChallenge';

interface Props {
  onContinueAsGuest: () => void;
  /** Open the public emergency report form without an account. */
  onReportEmergency?: () => void;
  notice?: string | null;
}

/** Sign-in and public registration. There is no portal choice: the server derives it from the verified account. Staff, administrator and
 *  developer accounts cannot be registered here (invitation only). Nothing on this screen offers or reveals a credential. */
export const LoginPage: React.FC<Props> = ({ onContinueAsGuest, onReportEmergency, notice }) => {
  const { login, register, completeMfa, sessionEnded } = useAuth();
  const [challenge, setChallenge] = useState<{ token: string; expiresIn: number } | null>(null);
  const [mode, setMode] = useState<'signin' | 'signup' | 'forgot'>('signin');
  const [info, setInfo] = useState<PortalInfo | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [remember, setRemember] = useState(false);
  const [signupRole, setSignupRole] = useState<'CITIZEN' | 'VOLUNTEER'>('CITIZEN');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [skills, setSkills] = useState('');
  const [area, setArea] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.getPortals().then(setInfo).catch(() => setInfo(null)); }, []);

  const signup = mode === 'signup';
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      if (signup) {
        await register({
          role: signupRole, username: username.trim().toLowerCase(), full_name: fullName.trim(), password, phone: phone.trim(), email: email.trim() || undefined,
          skills: signupRole === 'VOLUNTEER' ? skills.trim() : undefined, area: signupRole === 'VOLUNTEER' ? area.trim() : undefined,
        }, remember);
      } else {
        const r = await login(username, password, remember);
        if ('challenge' in r) { setPassword(''); setChallenge({ token: r.challenge, expiresIn: r.expiresIn }); }
      }
    } catch (err) {
      const msg = cleanMessage(err);
      setError(msg === 'Failed to fetch' ? 'Cannot reach the server. Check your connection and try again.' : msg);
    } finally {
      setBusy(false);
    }
  };

  if (challenge) {
    return (
      <AuthLayout>
        <MfaChallenge expiresInSeconds={challenge.expiresIn} onSubmit={(input) => completeMfa(challenge.token, input)} onCancel={() => { setChallenge(null); setError(null); }} />
      </AuthLayout>
    );
  }
  if (mode === 'forgot') {
    return <AuthLayout><ForgotPassword onBack={() => setMode('signin')} /></AuthLayout>;
  }

  return (
    <AuthLayout wide={signup}>
      <AuthHeading title={signup ? 'Create your account' : 'Sign in'} sub={signup ? 'For citizens and volunteers. Staff accounts are issued by invitation.' : 'Use the account you were given, or the one you registered.'} />
      {sessionEnded && !notice && <div className="auth-notice auth-notice-warn" role="status">Your session ended. For your security, please sign in again.</div>}
      {notice && <div className="auth-notice auth-notice-info" role="status">{notice}</div>}
      {info?.demo_mode && <div className="auth-notice auth-notice-warn" role="note">Development fixtures are enabled on this server (simulated accounts). Never use this configuration in production.</div>}

      <form onSubmit={submit} className="auth-form" noValidate>
        {signup && (
          <>
            <div className="auth-segment" role="radiogroup" aria-label="Account type">
              {(['CITIZEN', 'VOLUNTEER'] as const).map((r) => (
                <button key={r} type="button" role="radio" aria-checked={signupRole === r} onClick={() => setSignupRole(r)}>{r === 'CITIZEN' ? 'Citizen' : 'Volunteer'}</button>
              ))}
            </div>
            <TextField label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" required />
            <TextField label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" inputMode="tel" required hint="Used by the control room if they need to reach you about a report." />
            <TextField label="Email (optional)" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" hint="Needed later for password recovery. It must be verified before it can be used." />
            {signupRole === 'VOLUNTEER' && (
              <>
                <TextField label="Skills" value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="First aid, swimming, boat handling" required />
                <TextField label="Area" value={area} onChange={(e) => setArea(e.target.value)} placeholder="Where you can help, for example HSR Layout" required hint="A coordinator verifies volunteers before they can be assigned." />
              </>
            )}
          </>
        )}

        <TextField label={signup ? 'Choose a username' : 'Email or username'} value={username} onChange={(e) => setUsername(e.target.value)}
          autoComplete="username" autoCapitalize="none" spellCheck={false} required />

        <div className="rn-field">
          <label htmlFor="auth-password">Password</label>
          <div className="auth-pw">
            <input id="auth-password" className="rn-input" type={showPw ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={signup ? 'new-password' : 'current-password'} required aria-describedby={signup ? 'auth-pw-hint' : undefined} />
            <button type="button" onClick={() => setShowPw((v) => !v)} aria-label={showPw ? 'Hide password' : 'Show password'} aria-pressed={showPw}>
              {showPw ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </div>
          {signup && <span id="auth-pw-hint" className="rn-field-hint">At least 8 characters, mixing letters with numbers or symbols.</span>}
        </div>

        <div className="auth-row">
          <label className="auth-check">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            <span>Keep me signed in on this device<br /><span className="rn-field-hint">Applies to citizens and volunteers. Staff sessions always end after a shift.</span></span>
          </label>
          {!signup && <button type="button" className="link-btn" onClick={() => { setMode('forgot'); setError(null); }}>Forgot password?</button>}
        </div>

        {error && <div className="auth-notice auth-notice-error" role="alert">{error}</div>}

        <Button type="submit" variant="primary" block loading={busy} disabled={!username || !password}>{signup ? 'Create account' : 'Sign in'}</Button>
      </form>

      <p className="auth-foot">
        {signup ? 'Already registered? ' : 'New here? '}
        <button type="button" className="link-btn" onClick={() => { setMode(signup ? 'signin' : 'signup'); setError(null); }}>{signup ? 'Sign in' : 'Create a citizen or volunteer account'}</button>
      </p>

      <div className="auth-divider">or</div>
      <div className="auth-alt">
        <Button block icon={<Siren size={16} />} onClick={onReportEmergency ?? onContinueAsGuest}>Report an emergency without signing in</Button>
        <Button variant="ghost" block onClick={onContinueAsGuest}>View public flood information</Button>
      </div>
    </AuthLayout>
  );
};

