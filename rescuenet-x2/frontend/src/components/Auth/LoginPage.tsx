import React, { useEffect, useState } from 'react';
import { Eye, EyeOff, LifeBuoy, Radio, ShieldCheck, Terminal, Users } from 'lucide-react';
import { api } from '../../api/client';
import type { PortalId, PortalInfo } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { cleanMessage } from '../../lib/toast';
import { ForgotPassword } from './ForgotPassword';

const PORTAL_TABS: { id: PortalId; label: string; hint: string; icon: React.ElementType }[] = [
  { id: 'public', label: 'Citizens & Volunteers', hint: 'Report a flood, get warnings, offer help', icon: Users },
  { id: 'operations', label: 'Rescue Department', hint: 'Commanders, control room and field officers', icon: LifeBuoy },
  { id: 'admin', label: 'Admin & Developers', hint: 'Accounts, audit log and system settings', icon: Terminal },
];

interface Props {
  onContinueAsGuest: () => void;
  notice?: string | null;
}

export const LoginPage: React.FC<Props> = ({ onContinueAsGuest, notice }) => {
  const { login, register } = useAuth();
  const [portal, setPortal] = useState<PortalId>('public');
  const [mode, setMode] = useState<'signin' | 'signup' | 'forgot'>('signin');
  const [info, setInfo] = useState<PortalInfo | null>(null);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [remember, setRemember] = useState(false);

  // sign-up only
  const [signupRole, setSignupRole] = useState<'CITIZEN' | 'VOLUNTEER'>('CITIZEN');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [skills, setSkills] = useState('');
  const [area, setArea] = useState('');

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getPortals().then(setInfo).catch(() => setInfo(null));
  }, []);

  const switchPortal = (id: PortalId) => {
    setPortal(id);
    setMode('signin');
    setError(null);
    setPassword('');
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (portal === 'public' && mode === 'signup') {
        await register(
          {
            role: signupRole,
            username: username.trim().toLowerCase(),
            full_name: fullName.trim(),
            password,
            phone: phone.trim(),
            email: email.trim() || undefined,
            skills: signupRole === 'VOLUNTEER' ? skills.trim() : undefined,
            area: signupRole === 'VOLUNTEER' ? area.trim() : undefined,
          },
          remember,
        );
      } else {
        await login(portal, username, password, remember);
      }
    } catch (err) {
      const msg = cleanMessage(err);
      setError(msg === 'Failed to fetch' ? 'Cannot reach the server. Check that the backend is running.' : msg);
    } finally {
      setBusy(false);
    }
  };

  const fillDemo = (u: string) => {
    setUsername(u);
    setPassword(info?.demo_password || '');
    setMode('signin');
    setError(null);
  };

  const active = PORTAL_TABS.find((t) => t.id === portal)!;
  const demos = (info?.demo_accounts || []).filter((d) => d.portal === portal);
  const signup = portal === 'public' && mode === 'signup';

  return (
    <div className="login-shell">
      <aside className="login-brand">
        <div className="login-brand-inner">
          <div className="brand-badge">
            <Radio size={22} />
          </div>
          <h1>
            RescueNet <span className="text-cyan">X 2.0</span>
          </h1>
          <p className="login-tagline">Flood digital twin and rescue coordination for Bengaluru and Karnataka.</p>
          <ul className="login-points">
            <li>
              <ShieldCheck size={16} /> Flood risk from rainfall, humidity and temperature, with its measured accuracy shown
            </li>
            <li>
              <ShieldCheck size={16} /> Photos checked by AI, and every dispatch approved by a human commander
            </li>
            <li>
              <ShieldCheck size={16} /> LoRa mesh SOS packets located even without GPS
            </li>
          </ul>
          <p className="login-foot">Dr. ACS College of Engineering · Dept. of CSE (Data Science)</p>
        </div>
      </aside>

      <main className="login-panel">
        <div className="login-card">
          {mode === 'forgot' ? (
            <ForgotPassword onBack={() => setMode('signin')} />
          ) : (
            <>
          <h2>{signup ? 'Create your account' : 'Sign in'}</h2>
          <p className="login-sub">Choose how you use RescueNet.</p>

          {notice && <div className="form-notice form-notice-info">{notice}</div>}

          <div className="portal-tabs" role="tablist" aria-label="Sign-in portal">
            {PORTAL_TABS.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={portal === t.id}
                  className={`portal-tab ${portal === t.id ? 'portal-tab-active' : ''}`}
                  onClick={() => switchPortal(t.id)}
                >
                  <Icon size={16} />
                  <span>{t.label}</span>
                </button>
              );
            })}
          </div>
          <p className="portal-hint">{active.hint}</p>

          <form onSubmit={submit} className="login-form" noValidate>
            {signup && (
              <>
                <div className="seg-control" role="radiogroup" aria-label="Account type">
                  {(['CITIZEN', 'VOLUNTEER'] as const).map((r) => (
                    <button
                      key={r}
                      type="button"
                      role="radio"
                      aria-checked={signupRole === r}
                      className={signupRole === r ? 'seg-active' : ''}
                      onClick={() => setSignupRole(r)}
                    >
                      {r === 'CITIZEN' ? 'Citizen' : 'Volunteer'}
                    </button>
                  ))}
                </div>
                <label>
                  Full name
                  <input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" required />
                </label>
                <label>
                  Phone
                  <input value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" inputMode="tel" required />
                </label>
                <label>
                  Email <span className="optional">(optional)</span>
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
                </label>
                {signupRole === 'VOLUNTEER' && (
                  <>
                    <label>
                      Skills
                      <input value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="First aid, swimming, boat handling" required />
                    </label>
                    <label>
                      Area
                      <input value={area} onChange={(e) => setArea(e.target.value)} placeholder="Where you can help, e.g. HSR Layout" required />
                    </label>
                    <p className="field-help">A coordinator verifies volunteers before they can be assigned to a rescue.</p>
                  </>
                )}
              </>
            )}

            <label>
              {signup ? 'Choose a username' : 'Username or email'}
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
              />
            </label>

            <label>
              Password
              <div className="password-field">
                <input
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={signup ? 'new-password' : 'current-password'}
                  required
                />
                <button type="button" className="pw-toggle" onClick={() => setShowPw((v) => !v)} aria-label={showPw ? 'Hide password' : 'Show password'}>
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {signup && <span className="field-help">At least 8 characters, mixing letters with numbers or symbols.</span>}
            </label>

            <label className="check-row">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              Keep me signed in on this device (citizens and volunteers; staff sessions always end after a shift)
            </label>
            {!signup && (
              <button type="button" className="link-btn" onClick={() => { setMode('forgot'); setError(null); }}>
                Forgot your password?
              </button>
            )}

            {error && (
              <div className="form-notice form-notice-error" role="alert">
                {error}
              </div>
            )}

            <button className="btn-primary btn-block" type="submit" disabled={busy || !username || !password}>
              {busy ? 'Please wait…' : signup ? 'Create account' : 'Sign in'}
            </button>
          </form>

          {portal === 'public' ? (
            <p className="login-switch">
              {mode === 'signin' ? (
                <>
                  New here?{' '}
                  <button type="button" className="link-btn" onClick={() => { setMode('signup'); setError(null); }}>
                    Create an account
                  </button>
                </>
              ) : (
                <>
                  Already registered?{' '}
                  <button type="button" className="link-btn" onClick={() => { setMode('signin'); setError(null); }}>
                    Sign in
                  </button>
                </>
              )}
            </p>
          ) : (
            <p className="login-switch muted">Department and admin accounts are created by an administrator.</p>
          )}

          {info?.demo_mode && demos.length > 0 && mode === 'signin' && (
            <div className="demo-box">
              <strong>Demo accounts</strong>
              <span>Tap one to fill in the form (password: {info.demo_password}).</span>
              <div className="demo-chips">
                {demos.map((d) => (
                  <button key={d.username} type="button" className="chip" onClick={() => fillDemo(d.username)}>
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
          )}

            </>
          )}

          <div className="login-guest">
            <button type="button" className="btn-secondary btn-block" onClick={onContinueAsGuest}>
              Continue without signing in
            </button>
            <span>View flood warnings and shelters, or report an emergency.</span>
          </div>
        </div>
      </main>
    </div>
  );
};
