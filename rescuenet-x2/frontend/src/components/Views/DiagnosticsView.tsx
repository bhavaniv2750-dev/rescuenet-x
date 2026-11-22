import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import { toast } from '../../lib/toast';

type Section = Record<string, unknown>;

/** System health for administrators and developers. Counts and settings only: no personal data and no secrets. */
export const DiagnosticsView: React.FC = () => {
  const [diag, setDiag] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDiag(await api.getDiagnostics());
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Could not load diagnostics';
      setError(msg);
      toast.error(msg);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const warnings = (diag?.warnings as string[] | undefined) ?? [];
  const sections = Object.entries(diag ?? {}).filter(([k, v]) => k !== 'warnings' && v && typeof v === 'object') as [string, Section][];

  return (
    <div>
      <div className="view-header">
        <div>
          <h2>System diagnostics</h2>
          <p>Runtime, database counts, models and storage. No personal data or secrets are shown here.</p>
        </div>
        <button className="btn-secondary" onClick={load}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>
      {error && <p role="alert" className="text-orange">{error}</p>}
      {warnings.length > 0 && (
        <section className="panel" style={{ marginBottom: 16 }}>
          <h3>Warnings</h3>
          <ul>{warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </section>
      )}
      <div className="grid-2">
        {sections.map(([name, values]) => (
          <section key={name} className="panel">
            <h3 style={{ textTransform: 'capitalize' }}>{name.replace(/_/g, ' ')}</h3>
            <table className="data-table">
              <tbody>
                {Object.entries(values).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k.replace(/_/g, ' ')}</td>
                    <td>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}
      </div>
    </div>
  );
};
