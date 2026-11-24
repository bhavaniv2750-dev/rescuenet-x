import React, { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { ROLE_LABEL } from '../../auth/access';
import type { Capabilities, MfaStatus, SessionInfo } from '../../api/types';
import { MfaEnrollment } from '../Auth/MfaEnrollment';
import { DevOutbox } from '../Auth/DevOutbox';
import { cleanMessage, toast } from '../../lib/toast';

export const AccountView: React.FC = () => {
  const { user, logout, refreshUser } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [mfa, setMfa] = useState<MfaStatus | null>(null);
  const [enrolling, setEnrolling] = useState(false);
  const [newCodes, setNewCodes] = useState<string[] | null>(null);
  const [mfaNote, setMfaNote] = useState<string | null>(null);
  const [disablePw, setDisablePw] = useState('');
  // Sensitive actions need a RECENT second factor. When the server asks (X-MFA-Reauth-Required) we show a code prompt, then retry.
  const [reauth, setReauth] = useState<{ retry: () => Promise<void> } | null>(null);
  const [reauthCode, setReauthCode] = useState('');
  const [reauthError, setReauthError] = useState<string | null>(null);

  const loadMfa = useCallback(() => {
    api.mfaStatus().then(setMfa).catch(() => undefined);
  }, []);
  useEffect(() => {
    loadMfa();
  }, [loadMfa]);

  /** If the server wants a fresh authenticator code, remember what to retry afterwards and return true. */
  const handleError = (err: unknown, retry: () => Promise<void>): boolean => {
    if (err instanceof ApiError && err.reauth) {
      setReauthError(null);
      setReauthCode('');
      setReauth({ retry });
      return true;
    }
    return false;
  };

  const submitReauth = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.mfaReauth(reauthCode.replace(/\s/g, ''));
      const again = reauth?.retry;
      setReauth(null);
      if (again) await again();
    } catch (err) {
      setReauthError(cleanMessage(err));
      setReauthCode('');
    }
  };

  const regenerate = async () => {
    try {
      const r = await api.regenerateRecoveryCodes();
      setNewCodes(r.recovery_codes);
      loadMfa();
    } catch (err) {
      if (!handleError(err, regenerate)) setMfaNote(cleanMessage(err));
    }
  };

  const disableMfa = async () => {
    try {
      await api.mfaDisable(disablePw);
      setDisablePw('');
      setMfaNote('Two-step sign-in is turned off.');
      loadMfa();
      await refreshUser();
    } catch (err) {
      if (!handleError(err, disableMfa)) setMfaNote(cleanMessage(err));
    }
  };
  const [code, setCode] = useState('');
  const [verifyNote, setVerifyNote] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [newEmail, setNewEmail] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [contactPw, setContactPw] = useState('');

  useEffect(() => {
    api.getCapabilities().then(setCaps).catch(() => undefined);
  }, []);

  const sendCode = async (channel: 'email' | 'phone') => {
    try {
      const r = await api.requestVerification(channel);
      setVerifyNote(r.message);
      setTick((t) => t + 1);
    } catch (err) {
      setVerifyNote(cleanMessage(err));
    }
  };

  const confirmCode = async () => {
    try {
      await api.confirmVerification('email', code.trim());
      setCode('');
      setVerifyNote('Your email address is now verified.');
      await refreshUser();
    } catch (err) {
      setVerifyNote(cleanMessage(err));
    }
  };

  const saveContact = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const r = await api.changeContact({ current_password: contactPw, email: newEmail || undefined, phone: newPhone || undefined });
      setVerifyNote(r.message);
      setContactPw('');
      setNewEmail('');
      setNewPhone('');
      await refreshUser();
    } catch (err) {
      if (!handleError(err, () => saveContact(e))) setVerifyNote(cleanMessage(err));
    }
  };

  const loadSessions = useCallback(() => {
    api.getSessions().then((r) => setSessions(r.items)).catch(() => undefined);
  }, []);
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  if (!user) return null;

  const mismatch = again.length > 0 && next !== again;

  const change = async (e: React.FormEvent) => {
    e.preventDefault();
    if (next !== again) return;
    setBusy(true);
    try {
      await api.changePassword(current, next);
      toast.success('Password changed. Other devices were signed out.');
      loadSessions();
      setCurrent('');
      setNext('');
      setAgain('');
    } catch (err) {
      if (!handleError(err, () => change(e))) toast.error(cleanMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const row = (label: string, value?: string | null) => (
    <div className="kv-row">
      <span>{label}</span>
      <strong>{value || '—'}</strong>
    </div>
  );

  return (
    <div className="account-view">
      <div className="view-header">
        <div>
          <h2>My Account</h2>
          <p>Your profile and sign-in settings.</p>
        </div>
        <button className="btn-secondary" onClick={logout}>
          Sign out
        </button>
      </div>

      <div className="two-col">
        <section className="panel">
          <div className="panel-title-bar">
            <h3>Profile</h3>
          </div>
          <div className="kv-list">
            {row('Name', user.full_name)}
            {row('Username', user.username)}
            {row('Role', ROLE_LABEL[user.role])}
            {row('Email', user.email)}
            {row('Phone', user.phone)}
            {user.team_id && row('Team', user.team_id)}
            {user.volunteer_id && row('Volunteer ID', user.volunteer_id)}
          </div>
          {user.role === 'VOLUNTEER' && (
            <div className={`form-notice ${user.volunteer_verified ? 'form-notice-success' : 'form-notice-info'}`} style={{ marginTop: 12 }}>
              {user.volunteer_verified
                ? 'You are a verified volunteer and can be assigned to rescues.'
                : 'Waiting for a coordinator to verify you. You can be assigned to rescues after that.'}
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-title-bar">
            <h3>Change password</h3>
          </div>
          <form onSubmit={change} className="login-form">
            <label>
              Current password
              <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
            </label>
            <label>
              New password
              <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required />
              <span className="field-help">At least 8 characters, mixing letters with numbers or symbols.</span>
            </label>
            <label>
              Repeat new password
              <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
              {mismatch && <span className="field-error">The two passwords do not match.</span>}
            </label>
            <button className="btn-primary" disabled={busy || !current || !next || next !== again}>
              {busy ? 'Saving…' : 'Change password'}
            </button>
          </form>
        </section>
      </div>

      {reauth && (
        <form onSubmit={submitReauth} className="panel" style={{ marginTop: 16 }} aria-label="Confirm with your authenticator" role="alertdialog">
          <h3>Confirm it is you</h3>
          <p className="text-xs text-muted">This is a sensitive action. Enter the current 6-digit code from your authenticator app.</p>
          <input className="select-input" value={reauthCode} onChange={(e) => setReauthCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={8} aria-label="Authenticator code" autoFocus />{' '}
          <button className="btn-primary" disabled={reauthCode.replace(/\s/g, '').length < 6}>Confirm</button>{' '}
          <button type="button" className="btn-secondary" onClick={() => setReauth(null)}>Cancel</button>
          {reauthError && <div className="form-notice form-notice-error" role="alert" style={{ marginTop: 8 }}>{reauthError}</div>}
        </form>
      )}

      <section className="panel" style={{ marginTop: 16 }} aria-label="Two-step sign-in">
        <div className="panel-title-bar">
          <div>
            <h3>Two-step sign-in</h3>
            <p>{mfa?.required ? 'Required for your role.' : 'Optional for your role: adds a code from your phone to your password.'}</p>
          </div>
        </div>
        <div className="kv-list">
          {row('Status', mfa ? (mfa.enabled ? 'On' : 'Off') : '…')}
          {mfa?.enabled && row('Recovery codes left', String(mfa.recovery_codes_remaining))}
        </div>
        {mfa && !mfa.enabled && !enrolling && <button className="btn-primary" onClick={() => setEnrolling(true)}>Set up two-step sign-in</button>}
        {enrolling && <MfaEnrollment userName={user.full_name} onCancel={() => setEnrolling(false)} onDone={async () => { setEnrolling(false); loadMfa(); await refreshUser(); }} />}
        {mfa?.enabled && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 8 }}>
            <button className="btn-secondary" onClick={regenerate}>Generate new recovery codes</button>
            {mfa.can_disable && (
              <>
                <input className="select-input" type="password" placeholder="Current password" value={disablePw} onChange={(e) => setDisablePw(e.target.value)} aria-label="Current password to turn two-step sign-in off" autoComplete="current-password" />
                <button className="btn-secondary" disabled={!disablePw} onClick={disableMfa}>Turn off</button>
              </>
            )}
          </div>
        )}
        {mfa?.enabled && !mfa.can_disable && <p className="text-xs text-muted">Two-step sign-in cannot be turned off for your role. If you lose your authenticator, a server operator can reset it after verifying your identity.</p>}
        {newCodes && (
          <div className="form-notice form-notice-info" role="status" style={{ marginTop: 8 }}>
            <strong>New recovery codes (shown once; the old ones no longer work). Store them offline.</strong>
            <ul data-sensitive className="font-mono" style={{ columns: 2, listStyle: 'none', padding: 0 }}>{newCodes.map((c) => <li key={c}>{c}</li>)}</ul>
            <button className="btn-secondary" onClick={() => setNewCodes(null)}>I have stored them</button>
          </div>
        )}
        {mfaNote && <div className="form-notice form-notice-info" role="status" style={{ marginTop: 8 }}>{mfaNote}</div>}
      </section>

      <section className="panel" style={{ marginTop: 16 }} aria-label="Contact verification">
        <div className="panel-title-bar">
          <div>
            <h3>Contact details</h3>
            <p>
              A verified email address lets you recover your password. A changed address must be verified again.
              {caps && caps.email_delivery.transport === 'DEV_OUTBOX' && ' This is a development server: codes are not sent to real mailboxes.'}
              {caps && caps.email_delivery.transport === 'DISABLED' && ' This server has no email delivery configured, so email verification is unavailable.'}
            </p>
          </div>
        </div>
        <div className="kv-list">
          {row('Email', user.email ? `${user.email} (${user.email_verified ? 'verified' : 'not verified'})` : 'none')}
          {row('Phone', user.phone ? `${user.phone} (${user.phone_verified ? 'verified' : 'not verified'})` : 'none')}
        </div>
        {user.email && !user.email_verified && caps?.email_delivery.transport !== 'DISABLED' && (
          <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <button className="btn-secondary" onClick={() => sendCode('email')}>Send a verification code</button>
            <input className="select-input" placeholder="6-digit code" value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={12} aria-label="Verification code" />
            <button className="btn-primary" disabled={code.trim().length < 4} onClick={confirmCode}>Verify</button>
          </div>
        )}
        {user.phone && caps && !caps.phone_verification_available && (
          <p className="text-xs text-muted" style={{ marginTop: 8 }}>Phone verification is not available: no SMS provider is configured, so your number stays unverified.</p>
        )}
        {verifyNote && <div className="form-notice form-notice-info" role="status" style={{ marginTop: 12 }}>{verifyNote}</div>}
        <form onSubmit={saveContact} className="login-form" style={{ marginTop: 12 }}>
          <label>New email address<input type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} autoComplete="email" /></label>
          <label>New phone number<input value={newPhone} onChange={(e) => setNewPhone(e.target.value)} autoComplete="tel" /></label>
          <label>Current password (required to change contact details)<input type="password" value={contactPw} onChange={(e) => setContactPw(e.target.value)} autoComplete="current-password" /></label>
          <button className="btn-secondary" disabled={!contactPw || (!newEmail && !newPhone)}>Save contact details</button>
        </form>
        <DevOutbox refreshKey={tick} />
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title-bar">
          <div>
            <h3>Where you are signed in</h3>
            <p>Sign out of any device you do not recognise. Changing your password signs out every other device.</p>
          </div>
          <button
            className="btn-secondary"
            onClick={() => api.logoutAll().then(() => logout()).catch((e) => toast.error(cleanMessage(e)))}
          >
            Sign out everywhere
          </button>
        </div>
        <table className="data-table">
          <thead>
            <tr><th>Device</th><th>Signed in</th><th>Last active</th><th>Ends</th><th /></tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id}>
                <td>{s.user_agent ? s.user_agent.slice(0, 60) : 'Unknown device'} {s.current && <strong>(this device)</strong>}</td>
                <td>{new Date(s.created_at + 'Z').toLocaleString()}</td>
                <td>{new Date(s.last_used_at + 'Z').toLocaleString()}</td>
                <td>{new Date(s.expires_at + 'Z').toLocaleString()}</td>
                <td>
                  {!s.current && (
                    <button className="btn-secondary btn-xs" onClick={() => api.revokeSession(s.id).then(loadSessions).catch((e) => toast.error(cleanMessage(e)))}>
                      Sign out
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
};
