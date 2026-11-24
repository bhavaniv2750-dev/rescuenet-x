import { useAuth } from '../../auth/AuthContext';
import { Button } from '../ui';
import { AuthHeading, AuthLayout } from './AuthLayout';

/** A session that never completed MFA (for example one that pre-dates the rule) can do nothing: ask for a fresh sign-in. */
export const SessionNeedsSignIn: React.FC = () => {
  const { logout } = useAuth();
  return (
    <AuthLayout>
      <div role="alert" className="auth-form">
        <AuthHeading title="Please sign in again" sub="This session has not completed two-step sign-in. Sign in again to continue." />
        <Button variant="primary" block onClick={logout}>Sign in again</Button>
      </div>
    </AuthLayout>
  );
};
