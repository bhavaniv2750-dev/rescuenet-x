import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import { Button, ErrorState, PageHeader, Panel, Skeleton, StatusBadge } from '../ui';

type Section = Record<string, unknown>;

const show = (v: unknown): string => (v === null || v === undefined ? '—' : typeof v === 'boolean' ? (v ? 'yes' : 'no') : typeof v === 'object' ? JSON.stringify(v) : String(v));

/** System health for administrators and developers. Counts and settings only: no personal data and no secrets. Every figure comes from the
 *  server's diagnostics endpoint; nothing here is a fixed "OK" label. */
export const DiagnosticsView: React.FC = () => {
  const [diag, setDiag] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setDiag(await api.getDiagnostics()); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not load diagnostics'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const warnings = (diag?.warnings as string[] | undefined) ?? [];
  const sections = Object.entries(diag ?? {}).filter(([k, v]) => k !== 'warnings' && v && typeof v === 'object') as [string, Section][];

  return (
    <div>
      <PageHeader title="Diagnostics" description="Runtime, database counts, models, storage and configuration warnings, read from the server just now. No personal data or secrets are shown."
        actions={<Button icon={<RefreshCw size={14} />} onClick={load} loading={loading}>Refresh</Button>} />
      {error && <ErrorState title="Diagnostics unavailable" message={error} onRetry={load} />}
      {loading && !diag && <Skeleton rows={4} />}
      {diag && (
        <>
          <Panel title="Needs attention" actions={warnings.length ? <StatusBadge tone="warn">{warnings.length} warning{warnings.length > 1 ? 's' : ''}</StatusBadge> : <StatusBadge tone="ok">No warnings reported</StatusBadge>}>
            {warnings.length ? <ul className="diag-warnings">{warnings.map((w) => <li key={w}>{w}</li>)}</ul> : <p className="rn-field-hint">The server reported no configuration warnings. This does not mean every component is working: see the sections below for each service's own status.</p>}
          </Panel>
          <div className="diag-grid">
            {sections.map(([name, values]) => (
              <Panel key={name} title={name.replace(/_/g, ' ')} className="diag-card" flush>
                <div className="rn-table-wrap"><table className="rn-table"><caption className="rn-sr">{name}</caption>
                  <tbody>{Object.entries(values).map(([k, v]) => <tr key={k}><th scope="row" className="diag-k">{k.replace(/_/g, ' ')}</th><td className="auth-mono diag-v">{show(v)}</td></tr>)}</tbody></table></div>
              </Panel>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
