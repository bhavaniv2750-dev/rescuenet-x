import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { InvitationPreview } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { cleanMessage } from '../../lib/toast';

/** Opened from an invitation link (/#invite=TOKEN). The token lives in the URL fragment, which the browser never sends to a
 *  server; it is read once and removed from the address bar. The server tells us nothing unless the invitation is usable. */
export const AcceptInvitation: React.FC<{ token: string; onDone: () => void }> = ({ token, onDone }) => {
  const { adoptSession } = useAuth();
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [pw, setPw] = useState('');
  const [again, setAgain] = useState('');
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.inspectInvitation(token).then(setPreview).catch(() => setInvalid(true));
  }, [token]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.acceptInvitation({ token, username: username.trim(), full_name: fullName.trim(), password: pw, phone: phone.trim() || undefined });
      adoptSession(res);          // restricted session: the app then asks for email verification and MFA before anything else
      onDone();
    } catch (err) {
      setError(cleanMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (invalid) {
    return (
      <div className="login-panel">
        <div className="login-card" role="alert">
          <h2>This invitation cannot be used</h2>
          <p className="login-sub">It is invalid, expired or already used. Ask the person who invited you for a new one.</p>
          <button className="btn-primary btn-block" onClick={onDone}>Go to sign in</button>
        </div>
      </div>
    );
  }
  if (!preview) {
    return <div className="splash"><div className="spinner" aria-label="Checking invitation" /></div>;
  }
  return (
    <div className="login-panel">
      <div className="login-card">
        <h2>Activate your account</h2>
        <p className="login-sub">
          You are invited as <strong>{preview.role.replace('_', ' ').toLowerCase()}</strong>
          {preview.agency ? <> with <strong>{preview.agency}</strong></> : null}, for <span data-sensitive>{preview.recipient}</span>.
        </p>
        <ol className="muted" style={{ margin: '0 0 12px 18px' }}>{preview.steps.map((s) => <li key={s}>{s}</li>)}</ol>
        <form onSubmit={submit} className="login-form">
          <label>
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" pattern="[a-zA-Z0-9_.\-]{3,60}" required />
          </label>
          <label>
            Full name
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" required minLength={2} />
          </label>
          <label>
            Choose your password
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" required />
            <span className="field-help">Only you will ever know it. At least 8 characters, mixing letters with numbers or symbols.</span>
          </label>
          <label>
            Repeat password
            <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
            {again && pw !== again && <span className="field-error">The two passwords do not match.</span>}
          </label>
          <label>
            Phone (optional)
            <input value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" />
          </label>
          {error && <div className="form-notice form-notice-error" role="alert">{error}</div>}
          <button className="btn-primary btn-block" disabled={busy || !username || !fullName || !pw || pw !== again}>{busy ? 'Creating…' : 'Create my account'}</button>
          <button type="button" className="link-btn" onClick={onDone}>Cancel</button>
        </form>
      </div>
    </div>
  );
};
