import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { InvitationPreview } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { cleanMessage } from '../../lib/toast';
import { Button, TextField } from '../ui';
import { AuthHeading, AuthLayout } from './AuthLayout';

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
      <AuthLayout>
        <div role="alert" className="auth-form">
          <AuthHeading title="This invitation cannot be used" sub="It is invalid, expired or already used. Ask the person who invited you for a new one." />
          <Button variant="primary" block onClick={onDone}>Go to sign in</Button>
        </div>
      </AuthLayout>
    );
  }
  if (!preview) {
    return <div className="splash"><div className="spinner" aria-label="Checking invitation" /></div>;
  }
  return (
    <AuthLayout wide>
      <AuthHeading title="Activate your account" sub={<>You are invited as <strong>{preview.role.replace('_', ' ').toLowerCase()}</strong>{preview.agency ? <> with <strong>{preview.agency}</strong></> : null}, for <span data-sensitive>{preview.recipient}</span>.</>} />
      <ol className="rn-field-hint" style={{ paddingLeft: 18, lineHeight: 1.7 }}>{preview.steps.map((st) => <li key={st}>{st}</li>)}</ol>
      <form onSubmit={submit} className="auth-form">
        <TextField label="Username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" pattern="[a-zA-Z0-9_.\-]{3,60}" required hint="3 to 60 letters, numbers, dots, dashes or underscores." />
        <TextField label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" required minLength={2} />
        <TextField label="Choose your password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" required hint="Only you will ever know it. At least 8 characters, mixing letters with numbers or symbols." />
        <TextField label="Repeat password" type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required error={again && pw !== again ? 'The two passwords do not match.' : null} />
        <TextField label="Phone (optional)" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" />
        {error && <div className="auth-notice auth-notice-error" role="alert">{error}</div>}
        <Button type="submit" variant="primary" block loading={busy} disabled={!username || !fullName || !pw || pw !== again}>Create my account</Button>
        <button type="button" className="link-btn" onClick={onDone}>Cancel</button>
      </form>
    </AuthLayout>
  );
};
