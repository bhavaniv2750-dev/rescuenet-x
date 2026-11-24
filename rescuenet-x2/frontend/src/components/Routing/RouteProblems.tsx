import { AuthHeading, AuthLayout } from '../Auth/AuthLayout';
import { Button } from '../ui';

/** Shown when the address names a page this visitor may not open (Unauthorized) or no page at all (NotFound). The server decided
 *  which pages exist for the visitor; these screens never reveal what a forbidden page contains. */
export const UnauthorizedPage: React.FC<{ signedIn: boolean; onHome: () => void; onSignIn: () => void }> = ({ signedIn, onHome, onSignIn }) => (
  <AuthLayout>
    <div role="alert" className="auth-form">
      <AuthHeading title="You do not have access to this page"
        sub={signedIn ? 'Your account does not include this area. If you think it should, ask your administrator.' : 'This area is for signed-in staff. Sign in with your account to continue.'} />
      {signedIn ? <Button variant="primary" block onClick={onHome}>Go to my workspace</Button> : <Button variant="primary" block onClick={onSignIn}>Sign in</Button>}
      {!signedIn && <button type="button" className="link-btn" onClick={onHome}>Back to public information</button>}
    </div>
  </AuthLayout>
);

export const NotFoundPage: React.FC<{ onHome: () => void }> = ({ onHome }) => (
  <AuthLayout>
    <div role="alert" className="auth-form">
      <AuthHeading title="Page not found" sub="There is nothing at this address." />
      <Button variant="primary" block onClick={onHome}>Go to the start page</Button>
    </div>
  </AuthLayout>
);
