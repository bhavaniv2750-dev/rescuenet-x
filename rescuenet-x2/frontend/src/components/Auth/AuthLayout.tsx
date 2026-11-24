import { Radio } from 'lucide-react';

/** One layout for every authentication screen. Left (desktop): product mark only. Right: the form. Mobile: compact single column.
 *  The brand side intentionally carries no institution names, statistics, feature lists, credentials or affiliation claims. */
export const AuthLayout: React.FC<{ children: React.ReactNode; wide?: boolean; label?: string }> = ({ children, wide, label }) => (
  <div className="auth-shell" data-shell="auth">
    <aside className="auth-brand" aria-hidden="false">
      <svg className="auth-contours" viewBox="0 0 600 800" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
          <path key={i} d={`M-20 ${120 + i * 90} C 120 ${60 + i * 90}, 260 ${200 + i * 90}, 420 ${130 + i * 90} S 600 ${90 + i * 90}, 640 ${140 + i * 90}`} fill="none" stroke="currentColor" strokeWidth="1.2" />
        ))}
      </svg>
      <div className="auth-brand-mark">
        <span className="auth-logo" aria-hidden="true"><Radio size={26} /></span>
        <span className="auth-product">RescueNet <b>X 2.0</b></span>
      </div>
    </aside>
    <main className="auth-main" id="main" aria-label={label}>
      <div className="auth-mobile-brand" aria-hidden="true"><span className="auth-logo"><Radio size={20} /></span><span className="auth-product">RescueNet <b>X 2.0</b></span></div>
      <div className={`auth-card${wide ? ' auth-card-wide' : ''}`}>{children}</div>
    </main>
  </div>
);

export const AuthHeading: React.FC<{ title: string; sub?: React.ReactNode; id?: string }> = ({ title, sub, id }) => (
  <div className="auth-heading">
    <h1 id={id}>{title}</h1>
    {sub ? <p>{sub}</p> : null}
  </div>
);
