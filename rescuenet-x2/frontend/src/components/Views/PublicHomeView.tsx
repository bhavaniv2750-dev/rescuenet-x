import React, { useEffect, useState } from 'react';
import { AlertTriangle, Building2, LocateFixed, Phone, Siren, Waves } from 'lucide-react';
import { api } from '../../api/client';
import type { Alert, Facility, RiverGauge } from '../../api/types';
import type { Page } from '../../auth/access';

interface Props {
  alerts: Alert[];
  gauges: RiverGauge[];
  facilities: Facility[];
  userName?: string;
  onNavigate: (page: Page) => void;
}

const SEV_CLASS: Record<string, string> = { CRITICAL: 'sev-critical', HIGH: 'sev-high', WARNING: 'sev-warning', INFO: 'sev-info' };

const EMERGENCY_NUMBERS = [
  { n: '112', label: 'All emergencies' },
  { n: '108', label: 'Ambulance' },
  { n: '101', label: 'Fire' },
  { n: '100', label: 'Police' },
];

/** Landing page for citizens, volunteers and signed-out visitors. */
export const PublicHomeView: React.FC<Props> = ({ alerts, gauges, facilities, userName, onNavigate }) => {
  const [nearby, setNearby] = useState<Facility[] | null>(null);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);

  const active = alerts.filter((a) => a.status !== 'RESOLVED');
  const open = facilities.filter((f) => f.status !== 'FULL');
  const shelters = (nearby ?? open).filter((f) => f.facility_type === 'SHELTER' || f.facility_type === 'RELIEF_CAMP').slice(0, 4);

  useEffect(() => {
    setNearby(null);
  }, [facilities]);

  const findNearby = () => {
    if (!navigator.geolocation) {
      setLocError('Your browser cannot share its location.');
      return;
    }
    setLocating(true);
    setLocError(null);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const res = await api.getFacilities({ lat: pos.coords.latitude, lon: pos.coords.longitude });
          setNearby(res.items.filter((f) => f.status !== 'FULL'));
        } catch {
          setLocError('Could not load nearby shelters.');
        } finally {
          setLocating(false);
        }
      },
      () => {
        setLocError('Location permission was denied. Showing all open shelters.');
        setLocating(false);
      },
      { timeout: 8000 },
    );
  };

  return (
    <div className="public-home">
      <section className="hero-card">
        <div>
          <h2>{userName ? `Hello, ${userName.split(' ')[0]}` : 'Flood watch for Bengaluru'}</h2>
          <p>
            {active.length > 0
              ? `${active.length} flood warning${active.length > 1 ? 's' : ''} in force. Read them below and stay away from low-lying areas.`
              : 'No flood warnings are in force right now. Check back during heavy rain.'}
          </p>
        </div>
        <button className="btn-primary btn-lg" onClick={() => onNavigate('Report Emergency')}>
          <Siren size={18} /> Report an emergency
        </button>
      </section>

      <div className="home-grid">
        <section className="panel">
          <div className="panel-title-bar">
            <div>
              <h3>
                <AlertTriangle size={16} /> Warnings
              </h3>
              <p>Issued by the rescue control room</p>
            </div>
            <button className="link-btn" onClick={() => onNavigate('Emergency Alerts')}>
              See all
            </button>
          </div>
          {active.length === 0 ? (
            <div className="empty-state">
              <strong>All clear</strong>
              <span>No active warnings.</span>
            </div>
          ) : (
            <ul className="plain-list">
              {active.slice(0, 4).map((a) => (
                <li key={a.id} className="warning-row">
                  <span className={`sev-tag ${SEV_CLASS[a.severity] || ''}`}>{a.severity}</span>
                  <div>
                    <strong>{a.title}</strong>
                    <p>{a.message}</p>
                    <small>
                      {a.area} · within {a.radius_km} km · {new Date(a.created_at).toLocaleString()}
                    </small>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <div className="panel-title-bar">
            <div>
              <h3>
                <Building2 size={16} /> Shelters with space
              </h3>
              <p>{nearby ? 'Closest to you first' : 'Open shelters and relief camps'}</p>
            </div>
            <button className="btn-secondary btn-xs" onClick={findNearby} disabled={locating}>
              <LocateFixed size={13} /> {locating ? 'Locating…' : 'Near me'}
            </button>
          </div>
          {locError && <div className="form-notice form-notice-info">{locError}</div>}
          {shelters.length === 0 ? (
            <div className="empty-state">
              <strong>No open shelters listed</strong>
              <span>Call 112 if you need a safe place.</span>
            </div>
          ) : (
            <ul className="plain-list">
              {shelters.map((f) => (
                <li key={f.id} className="shelter-row">
                  <div>
                    <strong>{f.name}</strong>
                    <small>{f.address}</small>
                  </div>
                  <div className="shelter-meta">
                    <span>{Math.max(f.total_capacity - f.current_occupancy, 0)} places</span>
                    {f.distance_km !== undefined && <small>{f.distance_km} km</small>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <div className="panel-title-bar">
            <div>
              <h3>
                <Waves size={16} /> River gauge stations
              </h3>
              <p>{gauges.length} stations. Warning and danger levels only: live water readings are not connected.</p>
            </div>
            <button className="link-btn" onClick={() => onNavigate('Flood Forecasting')}>
              Forecast
            </button>
          </div>
          {gauges.length === 0 ? (
            <div className="empty-state">
              <strong>No gauge data</strong>
            </div>
          ) : (
            <ul className="plain-list">
              {gauges.slice(0, 4).map((g) => (
                <li key={g.gauge_id} className="shelter-row">
                  <div>
                    <strong>{g.station_name}</strong>
                    <small>
                      {g.river} · warning {g.warning_level_m} m · danger {g.danger_level_m} m
                    </small>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel emergency-numbers">
          <div className="panel-title-bar">
            <div>
              <h3>
                <Phone size={16} /> Emergency numbers
              </h3>
              <p>India, free to call</p>
            </div>
          </div>
          <div className="number-grid">
            {EMERGENCY_NUMBERS.map((e) => (
              <a key={e.n} href={`tel:${e.n}`} className="number-tile">
                <strong>{e.n}</strong>
                <span>{e.label}</span>
              </a>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
};
