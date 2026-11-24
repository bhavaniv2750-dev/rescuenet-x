import React from 'react';
import type { DashboardData, Incident } from '../../api/types';
import { DataNotice, SeverityBadge } from '../ui';
import { InteractiveMap } from '../Map/InteractiveMap';
import { AlertTriangle, ShieldCheck, Users, LifeBuoy, Bell, Activity, ArrowRight } from 'lucide-react';

interface OverviewViewProps {
  data: DashboardData | null;
  loading: boolean;
  onNavigate: (page: string) => void;
  onSelectIncident: (inc: Incident) => void;
  catchmentsGeoJSON: any;
  incidents: Incident[];
  alerts: any[];
  teams: any[];
  facilities: any[];
  gauges: any[];
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  data,
  loading,
  onNavigate,
  onSelectIncident,
  catchmentsGeoJSON,
  incidents,
  alerts,
  teams,
  facilities,
  gauges,
}) => {
  if (loading && !data) {
    return (
      <div className="view-loading">
        <div className="spinner" />
        <p>Loading command center data...</p>
      </div>
    );
  }

  const summary = data?.summary;
  const forecast = data?.forecast_preview;

  return (
    <div className="overview-container">
      <h1 className="rn-sr">Mission control overview</h1>
      <DataNotice items={incidents} noun="incidents" />
      {/* Top Telemetry KPI Bar */}
      <div className="metrics-grid">
        <div className="metric-card border-orange">
          <div className="metric-header">
            <span>ACTIVE INCIDENTS</span>
            <AlertTriangle className="icon text-orange" size={18} />
          </div>
          <div className="metric-body">
            <span className="metric-number">{String(summary?.active_incidents || 0).padStart(2, '0')}</span>
            <span className="metric-badge badge-orange">{summary?.critical_alerts || 0} Critical</span>
          </div>
          <div className="metric-footer">Records held in the RescueNet database</div>
        </div>

        <div className="metric-card border-red">
          <div className="metric-header">
            <span>PEOPLE AFFECTED</span>
            <Users className="icon text-red" size={18} />
          </div>
          <div className="metric-body">
            <span className="metric-number">{summary?.people_affected || 0}</span>
            <span className="metric-badge badge-blue">{summary?.people_rescued || 0} Rescued</span>
          </div>
          <div className="metric-footer">From citizen reports and LoRa SOS packets</div>
        </div>

        <div className="metric-card border-blue">
          <div className="metric-header">
            <span>SQUADS AVAILABLE</span>
            <LifeBuoy className="icon text-blue" size={18} />
          </div>
          <div className="metric-body">
            <span className="metric-number">{String(summary?.response_teams.available || 0).padStart(2, '0')}</span>
            <span className="metric-sub">of {summary?.response_teams.total || 0} squads</span>
          </div>
          <div className="metric-footer">Squads currently marked available</div>
        </div>

        <div className="metric-card border-emerald">
          <div className="metric-header">
            <span>SHELTER CAPACITY</span>
            <ShieldCheck className="icon text-emerald" size={18} />
          </div>
          <div className="metric-body">
            <span className="metric-number">{summary?.facilities.available_beds || 0}</span>
            <span className="metric-sub">open beds</span>
          </div>
          <div className="metric-footer">{summary?.facilities.total || 0} facilities listed</div>
        </div>
      </div>

      {/* Main Grid: Interactive Map + Triage Panel */}
      <div className="overview-main-grid">
        <div className="panel map-card">
          <div className="panel-title-bar">
            <div>
              <h3>Flood Digital Twin · Geospatial Operations View</h3>
              <p>IndoFloods Catchments & Active RescueNet Incidents across Bengaluru</p>
            </div>
            <button className="btn-secondary btn-sm" onClick={() => onNavigate('Flood Digital Twin')}>
              Full Screen Map →
            </button>
          </div>
          <InteractiveMap
            incidents={incidents}
            teams={teams}
            facilities={facilities}
            gauges={gauges}
            catchmentsGeoJSON={catchmentsGeoJSON}
            alerts={alerts}
            onSelectIncident={onSelectIncident}
            height="460px"
          />
        </div>

        {/* Right Intelligence Column */}
        <div className="overview-side-column">
          {/* Real AI ML Flood Risk Assessment */}
          <div className="panel forecast-card">
            <div className="panel-title-bar">
              <div>
                <h3>AI Flood Forecasting</h3>
                <p>
                  Example scenario ({forecast?.scenario_inputs?.rainfall_mm ?? '—'} mm/h rain, {forecast?.scenario_inputs?.water_level_m ?? '—'} m water level).
                  Enter real readings under Flood Forecasting.
                </p>
              </div>
              <Activity className="icon text-cyan" size={18} />
            </div>

            <div className="risk-level-box">
              <div className="risk-level-tag">
                <span className={`risk-dot ${forecast?.risk_level === 'CRITICAL' ? 'dot-red' : forecast?.risk_level === 'HIGH' ? 'dot-orange' : 'dot-yellow'}`} />
                <span>RISK LEVEL: <strong>{forecast?.risk_level || '—'}</strong></span>
              </div>
              <div className="probability-display">
                <span className="prob-value">{forecast ? `${Math.round(forecast.probability * 100)}%` : '—'}</span>
                <span className="prob-caption">Flood Probability</span>
              </div>

              {/* Multi-Horizon Projections */}
              <div className="horizons-row">
                <div className="horizon-item">
                  <span className="horizon-label">+30 MIN</span>
                  <span className="horizon-val">{forecast ? `${Math.round(forecast.horizon_30m * 100)}%` : '—'}</span>
                </div>
                <div className="horizon-item">
                  <span className="horizon-label">+45 MIN</span>
                  <span className="horizon-val">{forecast ? `${Math.round(forecast.horizon_45m * 100)}%` : '—'}</span>
                </div>
                <div className="horizon-item">
                  <span className="horizon-label">+60 MIN</span>
                  <span className="horizon-val">{forecast ? `${Math.round(forecast.horizon_60m * 100)}%` : '—'}</span>
                </div>
              </div>

              <div className="forecast-advisory">
                ⓘ {forecast?.advisory || 'No forecast loaded.'}
              </div>

              <button className="btn-primary btn-block" style={{ marginTop: '12px' }} onClick={() => onNavigate('Flood Forecasting')}>
                Run Scenario Simulator →
              </button>
            </div>
          </div>

          {/* Active Priority Incidents */}
          <div className="panel priority-incidents-card">
            <div className="panel-title-bar">
              <div>
                <h3>Priority Triage Queue</h3>
                <p>Field reports and LoRa SOS packets requiring response</p>
              </div>
              <button className="text-link" onClick={() => onNavigate('Rescue Operations')}>
                View all ({summary?.active_incidents || 0}) →
              </button>
            </div>

            <div className="incident-list">
              {data?.priority_incidents?.slice(0, 4).map((inc) => (
                <div key={inc.id} className="priority-incident-row" onClick={() => onNavigate('Rescue Operations')}>
                  <div className={`severity-stripe ${inc.severity.toLowerCase()}`} />
                  <div className="incident-details">
                    <div className="incident-row-top">
                      <span className="incident-code">{inc.id}</span>
                      <SeverityBadge severity={inc.severity} />
                    </div>
                    <div className="incident-location">{inc.location}</div>
                    <div className="incident-meta">
                      👥 {inc.people} affected · Status: <strong>{inc.status}</strong>
                    </div>
                  </div>
                  <ArrowRight size={16} className="text-muted" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Active Geo-Targeted Emergency Alerts Banner */}
      {data?.active_alerts_feed && data.active_alerts_feed.length > 0 && (
        <div className="active-alerts-banner">
          <div className="alert-banner-header">
            <Bell size={18} className="text-orange" />
            <strong>ALERTS IN FORCE ({data.active_alerts_feed.length})</strong>
          </div>
          <div className="alert-cards-row">
            {data.active_alerts_feed.map((alt) => (
              <div key={alt.id} className="mini-alert-card">
                <div className="mini-alert-top">
                  <SeverityBadge severity={alt.severity} />
                  <span className="text-muted font-mono">{alt.id}</span>
                </div>
                <div className="mini-alert-title">{alt.title}</div>
                <div className="mini-alert-meta">📍 {alt.area} · Radius {alt.radius_km} km · {alt.acknowledged_count} seen</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
