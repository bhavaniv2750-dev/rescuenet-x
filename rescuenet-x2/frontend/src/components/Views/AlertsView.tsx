import { SeverityBadge, DataNotice } from '../ui';
import React, { useState } from 'react';
import { cleanMessage, toast } from '../../lib/toast';
import { api, capUrl } from '../../api/client';
import type { Alert } from '../../api/types';
import { Check, Plus, Radio } from 'lucide-react';

interface AlertsViewProps {
  alerts: Alert[];
  onRefresh: () => void;
  /** Only operations staff issue and clear alerts; everyone else reads them. */
  canManage?: boolean;
  /** Commanders and administrators acknowledge alerts for the control room. */
  isCommander?: boolean;
}

export const AlertsView: React.FC<AlertsViewProps> = ({ alerts, onRefresh, canManage = false, isCommander = false }) => {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [area, setArea] = useState('Bellandur Basin, Bengaluru');
  const [severity, setSeverity] = useState('HIGH');
  const [radiusKm, setRadiusKm] = useState(3.0);
  const [lat, setLat] = useState(12.9352);
  const [lon, setLon] = useState(77.6778);
  const [submitting, setSubmitting] = useState(false);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const handleCreateAlert = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.createAlert({
        title,
        message,
        area,
        severity,
        radius_km: radiusKm,
        latitude: lat,
        longitude: lon,
      });
      setShowCreateModal(false);
      setTitle('');
      setMessage('');
      setActionNotice('Alert created. It is shown in this app and can be exported as CAP 1.2; it is not sent to phones.');
      onRefresh();
    } catch (err: any) {
      toast.error(cleanMessage(err) || 'Error creating alert');
    } finally {
      setSubmitting(false);
    }
  };

  const handleAcknowledge = async (id: string) => {
    try {
      await api.acknowledgeAlert(id);
      setActionNotice(`Alert ${id} acknowledged. Citizen receipt registered.`);
      onRefresh();
    } catch (err: any) {
      toast.error(cleanMessage(err));
    }
  };

  const handleResolve = async (id: string) => {
    try {
      await api.resolveAlert(id);
      setActionNotice(`Alert ${id} marked as RESOLVED.`);
      onRefresh();
    } catch (err: any) {
      toast.error(cleanMessage(err));
    }
  };

  return (
    <div className="alerts-container">
      <DataNotice items={alerts as { data_label?: string }[]} noun="alerts" />
      <div className="view-header">
        <div>
          <h1>Emergency alerts</h1>
          <p>
            Warnings for areas at risk, each with a target radius. They are shown in this app; they are not sent as SMS or push messages.
          </p>
        </div>
        {canManage && (
          <button className="btn-primary" onClick={() => setShowCreateModal(true)}>
            <Plus size={16} /> Issue Emergency Alert
          </button>
        )}
      </div>

      {actionNotice && (
        <div className="notice-banner banner-success">
          <Check size={16} />
          <span>{actionNotice}</span>
          <button className="btn-close" onClick={() => setActionNotice(null)}>✕</button>
        </div>
      )}

      {/* Alerts Active Grid */}
      <div className="alerts-grid">
        {alerts.map((alt) => {
          const isCritical = alt.severity === 'CRITICAL';
          const isHigh = alt.severity === 'HIGH';
          const isResolved = alt.status === 'RESOLVED';

          return (
            <div
              key={alt.id}
              className={`panel alert-card ${isResolved ? 'alert-resolved' : isCritical ? 'border-red' : isHigh ? 'border-orange' : 'border-yellow'}`}
            >
              <div className="alert-card-header">
                <div className="alert-badge-group">
                  <SeverityBadge severity={alt.severity} />
                  <span className={`status-pill ${isResolved ? 'pill-resolved' : 'pill-active'}`}>
                    {alt.status === 'ACTIVE' ? 'IN FORCE' : alt.status === 'ACKNOWLEDGED' ? 'IN FORCE · ACKNOWLEDGED' : alt.status}
                  </span>
                  {!isResolved && alt.status === 'ACTIVE' && (alt.escalation_level ?? 0) > 0 && (
                    <span className="sev-tag sev-critical" title="No commander has acknowledged this alert in time">
                      ESCALATED L{alt.escalation_level}
                    </span>
                  )}
                  {alt.data_label !== 'OBSERVED' && <span className="sev-tag sev-info" title="Example data shipped with the project">SAMPLE</span>}
                  <span className="font-mono text-muted text-xs">{alt.id}</span>
                </div>
                <div className="radius-tag">
                  <Radio size={12} className="pulse" />
                  <span>Radius: {alt.radius_km} km</span>
                </div>
              </div>

              <h3 className="alert-card-title">{alt.title}</h3>
              <p className="alert-card-message">{alt.message}</p>

              <div className="alert-card-meta">
                <div>📍 <strong>Target Area:</strong> {alt.area}</div>
                <div>📡 <strong>Shown in:</strong> this app. CAP 1.2 export available (no SMS or push is sent).</div>
                <div>👥 <strong>Seen by:</strong> {alt.acknowledged_count} {alt.acknowledged_count === 1 ? 'person' : 'people'}
                  {alt.acknowledged_by ? ` · acknowledged by ${alt.acknowledged_by}` : ''}</div>
                <div className="text-muted text-xs">🕒 Created: {new Date(alt.created_at).toLocaleString()}</div>
              </div>

              <div className="alert-card-actions">
                {!isResolved && (
                  <>
                    {isCommander ? (
                      alt.status === 'ACTIVE' && (
                        <button className="btn-primary btn-sm" onClick={() => handleAcknowledge(alt.id)}>
                          Acknowledge as commander
                        </button>
                      )
                    ) : (
                      <button className="btn-secondary btn-sm" onClick={() => handleAcknowledge(alt.id)}>
                        ✓ I have seen this
                      </button>
                    )}
                    {canManage && (
                      <button
                        className="btn-outline btn-sm text-red"
                        onClick={() => handleResolve(alt.id)}
                      >
                        Resolve / Clear
                      </button>
                    )}
                  </>
                )}
                <a className="btn-outline btn-sm" href={capUrl(alt.id)} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
                  CAP XML
                </a>
                {isResolved && (
                  <span className="text-muted text-xs">
                    Resolved at {alt.resolved_at ? new Date(alt.resolved_at).toLocaleTimeString() : 'N/A'}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Modal: Create Alert */}
      {showCreateModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <div className="modal-header">
              <h3>Create an alert</h3>
              <button className="icon-btn" onClick={() => setShowCreateModal(false)}>✕</button>
            </div>
            <form onSubmit={handleCreateAlert} className="modal-form">
              <label>
                Alert Title
                <input
                  required
                  placeholder="e.g. Flash Flood Surge Warning - Bellandur Spillway"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>

              <label>
                Target Geographical Area
                <input
                  required
                  placeholder="e.g. Bellandur Basin, Bengaluru"
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                />
              </label>

              <div className="form-row">
                <label>
                  Severity Level
                  <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                    <option value="CRITICAL">CRITICAL (Immediate Evacuation)</option>
                    <option value="HIGH">HIGH (Severe Waterlogging Risk)</option>
                    <option value="WARNING">WARNING (Monitor Telemetry)</option>
                    <option value="INFO">INFO (Advisory / Stage Responders)</option>
                  </select>
                </label>

                <label>
                  Target Radius (km)
                  <input
                    type="number"
                    step="0.5"
                    min="0.5"
                    max="25"
                    value={radiusKm}
                    onChange={(e) => setRadiusKm(parseFloat(e.target.value) || 1)}
                  />
                </label>
              </div>

              <div className="form-row">
                <label>
                  Center Latitude
                  <input
                    type="number"
                    step="0.0001"
                    value={lat}
                    onChange={(e) => setLat(parseFloat(e.target.value))}
                  />
                </label>

                <label>
                  Center Longitude
                  <input
                    type="number"
                    step="0.0001"
                    value={lon}
                    onChange={(e) => setLon(parseFloat(e.target.value))}
                  />
                </label>
              </div>

              <label>
                Emergency Advisory Message
                <textarea
                  required
                  rows={3}
                  placeholder="Clear instructions for citizens and responders within the targeted boundary..."
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                />
              </label>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Persisting Alert...' : 'Issue Alert Now'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
