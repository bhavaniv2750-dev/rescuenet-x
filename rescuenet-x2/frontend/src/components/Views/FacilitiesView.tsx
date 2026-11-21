import React, { useState } from 'react';
import type { Facility } from '../../api/types';
import { Hospital, Tent, Shield, Phone, MapPin } from 'lucide-react';

interface FacilitiesViewProps {
  facilities: Facility[];
  onRefresh?: () => void;
}

export const FacilitiesView: React.FC<FacilitiesViewProps> = ({ facilities }) => {
  const [filterType, setFilterType] = useState<string>('ALL');

  const filtered = filterType === 'ALL'
    ? facilities
    : facilities.filter((f) => f.facility_type === filterType);

  const getIcon = (type: string) => {
    switch (type) {
      case 'HOSPITAL':
        return <Hospital className="text-pink" size={18} />;
      case 'SHELTER':
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
            Real shelter capacities, hospital emergency bed intake, and calculated distances from Bengaluru Central.
          </p>
        </div>
        <div className="filter-group">
          {['ALL', 'HOSPITAL', 'SHELTER', 'RELIEF_CAMP', 'RESCUE_HQ'].map((t) => (
            <button
              key={t}
              className={`filter-btn ${filterType === t ? 'active' : ''}`}
              onClick={() => setFilterType(t)}
            >
              {t.replace('_', ' ')}
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
                  <span>{fac.facility_type.replace('_', ' ')}</span>
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
                  <span className="font-mono">{fac.current_occupancy} / {fac.total_capacity} beds</span>
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
                  ✓ <strong>{avail}</strong> beds currently available for evacuation intake
                </div>
              </div>

              <div className="facility-card-footer">
                <a href={`tel:${fac.contact}`} className="btn-secondary btn-sm" style={{ textDecoration: 'none' }}>
                  <Phone size={14} /> Call {fac.contact}
                </a>
                <span className="status-pill pill-active">{fac.status}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
