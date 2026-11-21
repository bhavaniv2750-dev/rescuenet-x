import React, { useState } from 'react';
import { api } from '../../api/client';
import { cleanMessage, toast } from '../../lib/toast';
import type { Facility } from '../../api/types';
import { Hospital, Tent, Shield, Phone, MapPin } from 'lucide-react';

interface FacilitiesViewProps {
  facilities: Facility[];
  onRefresh?: () => void;
  /** Operations staff can update how many people a facility holds. */
  canManage?: boolean;
}

const TYPE_LABEL: Record<string, string> = {
  HOSPITAL: 'Hospital', SHELTER: 'Shelter', RELIEF_CAMP: 'Relief camp', RESCUE_HQ: 'Rescue HQ',
  POLICE_STATION: 'Police station', FIRE_STATION: 'Fire station', SCHOOL: 'School shelter',
};
const UNIT_LABEL: Record<string, string> = { HOSPITAL: 'beds', FIRE_STATION: 'places', POLICE_STATION: 'places', RESCUE_HQ: 'places' };

export const FacilitiesView: React.FC<FacilitiesViewProps> = ({ facilities, onRefresh, canManage = false }) => {
  const [filterType, setFilterType] = useState<string>('ALL');
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState('');

  const saveOccupancy = async (f: Facility) => {
    const n = Number(draft);
    if (!Number.isInteger(n) || n < 0 || n > f.total_capacity) {
      toast.error(`Enter a whole number from 0 to ${f.total_capacity}.`);
      return;
    }
    try {
      await api.updateFacilityOccupancy(f.id, n);
      toast.success(`${f.name} updated.`);
      setEditing(null);
      onRefresh?.();
    } catch (err) {
      toast.error(cleanMessage(err));
    }
  };

  const filtered = filterType === 'ALL'
    ? facilities
    : facilities.filter((f) => f.facility_type === filterType);

  const getIcon = (type: string) => {
    switch (type) {
      case 'HOSPITAL':
        return <Hospital className="text-pink" size={18} />;
      case 'SHELTER':
      case 'SCHOOL':
      case 'RELIEF_CAMP':
        return <Tent className="text-emerald" size={18} />;
      default:
        return <Shield className="text-blue" size={18} />;
    }
  };

  return (
    <div className="facilities-container">
      <div className="view-header">
        <div>
          <h2>Emergency Facilities, Hospitals & Evacuation Shelters</h2>
          <p>
            Shelter and hospital capacity, with distance from central Bengaluru. Entries marked SAMPLE are example data shipped with the project; staff-entered facilities are marked ENTERED.
          </p>
        </div>
        <div className="filter-group">
          {['ALL', 'HOSPITAL', 'SHELTER', 'SCHOOL', 'RELIEF_CAMP', 'RESCUE_HQ', 'FIRE_STATION', 'POLICE_STATION'].map((t) => (
            <button
              key={t}
              className={`filter-btn ${filterType === t ? 'active' : ''}`}
              onClick={() => setFilterType(t)}
            >
              {t === 'ALL' ? 'All' : TYPE_LABEL[t]}
            </button>
          ))}
        </div>
      </div>

      <div className="facilities-grid">
        {filtered.map((fac) => {
          const avail = fac.total_capacity - fac.current_occupancy;
          const occPct = Math.round((fac.current_occupancy / fac.total_capacity) * 100);

          return (
            <div key={fac.id} className="panel facility-card">
              <div className="facility-card-top">
                <div className="facility-type-tag">
                  {getIcon(fac.facility_type)}
                  <span>{TYPE_LABEL[fac.facility_type] || fac.facility_type}</span>
                </div>
                <div className="facility-dist-tag font-mono">
                  📍 {fac.distance_km !== undefined ? `${fac.distance_km} km` : 'Near'}
                </div>
              </div>

              <h3 className="facility-name">{fac.name}</h3>
              <div className="facility-address">
                <MapPin size={14} className="text-muted" />
                <span>{fac.address}</span>
              </div>

              {/* Occupancy Progress Bar */}
              <div className="occupancy-section">
                <div className="occupancy-meta">
                  <span>Occupancy ({occPct}%)</span>
                  <span className="font-mono">{fac.current_occupancy} / {fac.total_capacity} {UNIT_LABEL[fac.facility_type] || 'places'}</span>
                </div>
                <div className="progress-track">
                  <div
                    className="progress-fill"
                    style={{
                      width: `${occPct}%`,
                      backgroundColor: occPct > 85 ? '#ef4444' : occPct > 60 ? '#f97316' : '#10b981',
                    }}
                  />
                </div>
                <div className="avail-beds-text">
                  ✓ <strong>{avail}</strong> {UNIT_LABEL[fac.facility_type] || 'places'} free
                </div>
              </div>

              {canManage && (
                <div className="occupancy-edit">
                  {editing === fac.id ? (
                    <>
                      <input type="number" min={0} max={fac.total_capacity} value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Current occupancy" />
                      <button className="btn-primary btn-xs" onClick={() => saveOccupancy(fac)}>Save</button>
                      <button className="btn-secondary btn-xs" onClick={() => setEditing(null)}>Cancel</button>
                    </>
                  ) : (
                    <button className="btn-secondary btn-xs" onClick={() => { setEditing(fac.id); setDraft(String(fac.current_occupancy)); }}>
                      Update occupancy
                    </button>
                  )}
                </div>
              )}

              <div className="facility-card-footer">
                <a href={`tel:${fac.contact}`} className="btn-secondary btn-sm" style={{ textDecoration: 'none' }}>
                  <Phone size={14} /> Call {fac.contact}
                </a>
                <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span className="sev-tag sev-info" title="Where this entry came from">{fac.data_label === 'OBSERVED' ? 'ENTERED' : 'SAMPLE'}</span>
                  <span className={`status-pill ${fac.status === 'FULL' ? 'pill-critical' : fac.status === 'NEAR_CAPACITY' ? 'pill-amber' : 'pill-active'}`}>{fac.status.replace('_', ' ')}</span>
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
