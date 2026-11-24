import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react';
import { Button } from './Button';

export const EmptyState: React.FC<{ title: string; children?: React.ReactNode; action?: React.ReactNode; icon?: React.ReactNode }> = ({ title, children, action, icon }) => (
  <div className="rn-state" role="status">
    <span className="rn-state-icon" aria-hidden="true">{icon ?? <Inbox size={22} />}</span>
    <strong>{title}</strong>
    {children ? <p>{children}</p> : null}
    {action}
  </div>
);

export const ErrorState: React.FC<{ title?: string; message: string; onRetry?: () => void }> = ({ title = 'Something went wrong', message, onRetry }) => (
  <div className="rn-state rn-state-error" role="alert">
    <span className="rn-state-icon" aria-hidden="true"><AlertTriangle size={22} /></span>
    <strong>{title}</strong>
    <p>{message}</p>
    {onRetry ? <Button size="sm" icon={<RefreshCw size={14} />} onClick={onRetry}>Try again</Button> : null}
  </div>
);

/** Loading placeholder. Announces itself to assistive technology; decorative shimmer respects reduced motion. */
export const Skeleton: React.FC<{ rows?: number; height?: number; label?: string }> = ({ rows = 3, height = 56, label = 'Loading' }) => (
  <div className="rn-skeleton-stack" role="status" aria-label={label} aria-busy="true">
    {Array.from({ length: rows }, (_, i) => <div key={i} className="rn-skeleton" style={{ height }} />)}
  </div>
);
