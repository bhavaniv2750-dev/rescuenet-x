import { useAuth } from '../../auth/AuthContext';

/** A session that never completed MFA (for example one that pre-dates the rule) can do nothing: ask for a fresh sign-in. */
export const SessionNeedsSignIn: React.FC = () => {
  const { logout } = useAuth();
  return (
    <div className="login-panel">
      <div className="login-card" role="alert">
        <h2>Please sign in again</h2>
        <p className="login-sub">This session has not completed two-step sign-in. Sign in again to continue.</p>
        <button className="btn-primary btn-block" onClick={logout}>Sign in again</button>
      </div>
    </div>
  );
};
