import { CircleAlert, Info, OctagonAlert, TriangleAlert } from 'lucide-react';
import type { Provenance, Severity } from '../../design/tokens';

const SEV: Record<Severity, { icon: React.ElementType; label: string }> = {
  CRITICAL: { icon: OctagonAlert, label: 'Critical' },
  HIGH: { icon: TriangleAlert, label: 'High' },
  MODERATE: { icon: CircleAlert, label: 'Moderate' },
  LOW: { icon: Info, label: 'Low' },
};

/** Severity is shown with a distinct icon shape AND a text label, never colour alone. */
export const SeverityBadge: React.FC<{ severity: string; compact?: boolean }> = ({ severity, compact }) => {
  const key = (severity || '').toUpperCase() as Severity;
  const s = SEV[key];
  if (!s) return <span className="rn-badge rn-badge-neutral">{severity || '—'}</span>;
  const Icon = s.icon;
  return (
    <span className={`rn-badge rn-sev rn-sev-${key.toLowerCase()}`} title={`Severity: ${s.label}`}>
      <Icon size={13} aria-hidden="true" />
      {compact ? <span className="rn-sr">Severity: </span> : null}
      <span>{s.label}</span>
    </span>
  );
};

export type Tone = 'neutral' | 'ok' | 'warn' | 'danger' | 'info';
/** Generic status chip: text always present; the dot is decoration. */
export const StatusBadge: React.FC<{ tone?: Tone; children: React.ReactNode; title?: string }> = ({ tone = 'neutral', children, title }) => (
  <span className={`rn-badge rn-badge-${tone}`} title={title}>
    <span className="rn-dot" aria-hidden="true" />
    {children}
  </span>
);

const PROV_HELP: Record<Provenance, string> = {
  SIMULATED: 'Generated for demonstration; not a real event or measurement.',
  HISTORICAL: 'Recorded in the past; not current.',
  OBSERVED: 'Measured or reported by a real source.',
  LIVE: 'Updating from a connected source right now.',
  STALE: 'Was live, but has not updated recently.',
  UNAVAILABLE: 'Not available at the moment.',
};
/** Data provenance. LIVE must only be used where the data source genuinely supports it. */
export const ProvenanceBadge: React.FC<{ kind: Provenance }> = ({ kind }) => (
  <span className={`rn-badge rn-prov rn-prov-${kind.toLowerCase()}`} title={PROV_HELP[kind]}>
    {kind}
  </span>
);
