import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import type { Capabilities } from '../../api/types';
import { useTheme } from '../../lib/theme';
import { Button, PageHeader, Panel, ProvenanceBadge, StatusBadge } from '../ui';

interface Props { backendStatus?: string; onRefresh?: () => void }  // onRefresh kept for the shell's call signature

const LOCAL_KEYS = ['rescuenet.sidebar.collapsed', 'rescuenet.guest', 'rescuenet.theme', 'rescuenet.maptheme', 'rescuenet.mapstyle', 'rescuenet.basemap'];
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000/api';

/** Read-only view of what this deployment can really do, plus the few preferences stored in this browser. There are no fake switches: a
 *  setting appears here only if it changes something. Nothing is stored on the server from this page. */
export const SettingsView: React.FC<Props> = ({ backendStatus }) => {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cleared, setCleared] = useState(false);

  const load = useCallback(async () => {
    setErr(null);
    const [c, h] = await Promise.allSettled([api.getCapabilities(), api.checkHealth()]);
    setCaps(c.status === 'fulfilled' ? c.value : null);
    setHealth(h.status === 'fulfilled' ? (h.value as Record<string, unknown>) : null);
    if (c.status === 'rejected' || h.status === 'rejected') setErr('One or more status checks failed. The values below are what could be read.');
  }, []);
  useEffect(() => { load(); }, [load]);

  const { app: appPref, setAppTheme, map: mapPref, setMapAppearance } = useTheme();
  const email = caps?.email_delivery;
  return (
    <div className="settings-page">
      <PageHeader title="Settings" description="What this deployment can actually do right now, and the preferences kept in this browser." actions={<Button icon={<RefreshCw size={14} />} onClick={load}>Re-check</Button>} />
      {err && <div className="auth-notice auth-notice-warn" role="alert">{err}</div>}
      <div className="diag-grid">
        <Panel title="Server">
          <dl className="fc-dl">
            <dt>Connection</dt><dd><StatusBadge tone={backendStatus === 'Connected' ? 'ok' : 'danger'}>{backendStatus || 'unknown'}</StatusBadge></dd>
            <dt>API address</dt><dd className="auth-mono">{API_BASE}</dd>
            <dt>Health endpoint</dt><dd>{health ? <StatusBadge tone="ok">answered</StatusBadge> : <StatusBadge tone="danger">no answer</StatusBadge>}</dd>
            <dt>Environment</dt><dd className="auth-mono">{caps?.environment ?? '—'}</dd>
          </dl>
        </Panel>
        <Panel title="Notification delivery">
          <dl className="fc-dl">
            <dt>Email</dt>
            <dd>
              {!email ? '—' : email.transport === 'SMTP' ? <StatusBadge tone="info">SMTP configured (delivery not verified)</StatusBadge>
                : email.transport === 'DEV_OUTBOX' ? <StatusBadge tone="warn">Development outbox: nothing is delivered</StatusBadge>
                : <StatusBadge tone="danger">Unavailable: no email provider configured</StatusBadge>}
            </dd>
            <dt>SMS / phone</dt><dd><StatusBadge tone="danger">Unavailable: no SMS provider is integrated</StatusBadge></dd>
            <dt>Push notifications</dt><dd><StatusBadge tone="danger">Not implemented</StatusBadge></dd>
            <dt>Alerts</dt><dd>Shown inside this app, with CAP 1.2 export. They are not sent to phones.</dd>
          </dl>
        </Panel>
        <Panel title="Appearance">
          <p className="rn-field-hint">The application theme and the map appearance are independent. System follows your operating system setting.</p>
          <label className="map-select">Application theme
            <select value={appPref} onChange={(e) => setAppTheme(e.target.value as 'system' | 'light' | 'dark')}>
              <option value="light">Light</option><option value="dark">Dark</option><option value="system">System default</option>
            </select>
          </label>
          <label className="map-select" style={{ marginTop: 12 }}>Map appearance
            <select value={mapPref} onChange={(e) => setMapAppearance(e.target.value as 'follow' | 'light' | 'dark')}>
              <option value="follow">Follow application theme</option><option value="light">Always light</option><option value="dark">Always dark</option>
            </select>
          </label>
        </Panel>
        <Panel title="This browser">
          <p className="rn-field-hint">Only convenience choices are stored here (for example whether the sidebar is collapsed). Nothing sensitive, and nothing is sent to the server.</p>
          <Button onClick={() => { try { LOCAL_KEYS.forEach((k) => localStorage.removeItem(k)); setCleared(true); } catch { setCleared(false); } }}>Forget these preferences</Button>
          {cleared && <span className="rn-field-hint" role="status"> Cleared. They take effect on the next page load.</span>}
        </Panel>
        <Panel title="About this software">
          <p className="rn-field-hint">RescueNet X 2.0 is a student-built prototype. Its datasets are simulated or historical: <ProvenanceBadge kind="SIMULATED" /> <ProvenanceBadge kind="HISTORICAL" />. It is not connected to any emergency authority and is not an official warning system.</p>
        </Panel>
      </div>
    </div>
  );
};
