/** Consistent page header: one h1 per page, optional description, provenance/status slot and actions. */
export const PageHeader: React.FC<{ title: string; description?: React.ReactNode; meta?: React.ReactNode; actions?: React.ReactNode }> = ({ title, description, meta, actions }) => (
  <header className="rn-page-head">
    <div className="rn-page-head-text">
      <h1>{title}</h1>
      {description ? <p>{description}</p> : null}
      {meta ? <div className="rn-page-meta">{meta}</div> : null}
    </div>
    {actions ? <div className="rn-page-actions">{actions}</div> : null}
  </header>
);

export const Panel: React.FC<{ title?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode; flush?: boolean; className?: string }> = ({ title, actions, children, flush, className = '' }) => (
  <section className={`rn-panel ${className}`.trim()}>
    {title || actions ? <div className="rn-panel-head">{title ? <h2>{title}</h2> : <span />}{actions}</div> : null}
    <div className={flush ? 'rn-panel-flush' : 'rn-panel-body'}>{children}</div>
  </section>
);
