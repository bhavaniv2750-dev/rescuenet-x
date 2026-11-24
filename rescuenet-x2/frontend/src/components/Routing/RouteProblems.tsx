/** Shown when the address names a page this visitor may not open (Unauthorized) or no page at all (NotFound). The server decided
 *  which pages exist for the visitor; these screens never reveal what a forbidden page contains. */
export const UnauthorizedPage: React.FC<{ signedIn: boolean; onHome: () => void; onSignIn: () => void }> = ({ signedIn, onHome, onSignIn }) => (
  <div className="login-panel">
    <div className="login-card" role="alert">
      <h2>You do not have access to this page</h2>
      <p className="login-sub">
        {signedIn
          ? 'Your account does not include this area. If you think it should, ask your administrator.'
          : 'This area is for signed-in staff. Sign in with your account to continue.'}
      </p>
      {signedIn ? (
        <button className="btn-primary btn-block" onClick={onHome}>Go to my workspace</button>
      ) : (
        <button className="btn-primary btn-block" onClick={onSignIn}>Sign in</button>
      )}
      {!signedIn && <button className="link-btn" onClick={onHome}>Back to public information</button>}
    </div>
  </div>
);

export const NotFoundPage: React.FC<{ onHome: () => void }> = ({ onHome }) => (
  <div className="login-panel">
    <div className="login-card" role="alert">
      <h2>Page not found</h2>
      <p className="login-sub">There is nothing at this address.</p>
      <button className="btn-primary btn-block" onClick={onHome}>Go to the start page</button>
    </div>
  </div>
);
