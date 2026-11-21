import React, { useState } from 'react';
import { cleanMessage, toast } from '../../lib/toast';
import { api } from '../../api/client';
import type { Volunteer } from '../../api/types';
import { Shield, Plus, CheckCircle, XCircle } from 'lucide-react';

interface VolunteersViewProps {
  volunteers: Volunteer[];
  onRefresh: () => void;
}

export const VolunteersView: React.FC<VolunteersViewProps> = ({ volunteers, onRefresh }) => {
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [skills, setSkills] = useState('Certified Swimmer, First Aid CPR');
  const [area, setArea] = useState('Indiranagar, Bengaluru');
  const [filterVerified, setFilterVerified] = useState<string>('ALL');
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.registerVolunteer({ name, phone, email, skills, area });
      setShowRegisterModal(false);
      setName('');
      setPhone('');
      setEmail('');
      setNotice('Volunteer registered successfully! Status is pending verification.');
      onRefresh();
    } catch (err: any) {
      toast.error(cleanMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleVerified = async (v: Volunteer) => {
    try {
      await api.updateVolunteer(v.id, { is_verified: !v.is_verified });
      setNotice(`Updated verification for ${v.name}: ${!v.is_verified ? 'VERIFIED' : 'UNVERIFIED'}`);
      onRefresh();
    } catch (err: any) {
      toast.error(cleanMessage(err));
    }
  };

  const filtered = volunteers.filter((v) => {
    if (filterVerified === 'VERIFIED' && !v.is_verified) return false;
    if (filterVerified === 'UNVERIFIED' && v.is_verified) return false;
    return true;
  });

  return (
    <div className="volunteers-container">
      <div className="view-header">
        <div>
          <h2>Verified Volunteer & Civilian Response Network</h2>
          <p>
            Civilian response force with verified swim credentials, medical skills, and emergency coordination.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowRegisterModal(true)}>
          <Plus size={16} /> Register Volunteer
        </button>
      </div>

      {notice && (
        <div className="notice-banner banner-success">
          <span>{notice}</span>
          <button className="btn-close" onClick={() => setNotice(null)}>✕</button>
        </div>
      )}

      {/* Filter tabs */}
      <div className="filter-bar">
        <div className="filter-group">
          <span>Verification Status:</span>
          {['ALL', 'VERIFIED', 'UNVERIFIED'].map((f) => (
            <button
              key={f}
              className={`filter-btn ${filterVerified === f ? 'active' : ''}`}
              onClick={() => setFilterVerified(f)}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="stats-badges">
          <span className="badge"><Shield size={14} className="text-emerald" /> {volunteers.filter((v) => v.is_verified).length} Verified Responders</span>
        </div>
      </div>

      <div className="panel volunteer-table-card">
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>NAME</th>
                <th>SECTOR / AREA</th>
                <th>SPECIALIZED SKILLS</th>
                <th>CONTACT</th>
                <th>VERIFICATION</th>
                <th>STATUS</th>
                <th>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((vol) => (
                <tr key={vol.id}>
                  <td className="font-mono text-cyan">{vol.id}</td>
                  <td>
                    <strong>{vol.name}</strong>
                  </td>
                  <td>📍 {vol.area}</td>
                  <td>
                    <span className="skill-pill">{vol.skills}</span>
                  </td>
                  <td className="font-mono text-xs text-muted">
                    {vol.phone}<br/>{vol.email}
                  </td>
                  <td>
                    {vol.is_verified ? (
                      <span className="status-pill pill-verified">
                        <CheckCircle size={12} /> VERIFIED
                      </span>
                    ) : (
                      <span className="status-pill pill-unverified">
                        <XCircle size={12} /> UNVERIFIED
                      </span>
                    )}
                  </td>
                  <td>
                    <span className={`status-pill ${vol.status === 'AVAILABLE' ? 'pill-active' : 'pill-deployed'}`}>
                      {vol.status}
                    </span>
                  </td>
                  <td>
                    <button
                      className="btn-outline btn-xs"
                      onClick={() => handleToggleVerified(vol)}
                    >
                      {vol.is_verified ? 'Revoke Verify' : 'Grant Verified ✓'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal: Register Volunteer */}
      {showRegisterModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <div className="modal-header">
              <h3>Register Emergency Volunteer</h3>
              <button className="icon-btn" onClick={() => setShowRegisterModal(false)}>✕</button>
            </div>
            <form onSubmit={handleRegister} className="modal-form">
              <label>
                Full Name
                <input required placeholder="e.g. Ramesh Kumar" value={name} onChange={(e) => setName(e.target.value)} />
              </label>

              <div className="form-row">
                <label>
                  Phone Number
                  <input required placeholder="+91 98450 XXXXX" value={phone} onChange={(e) => setPhone(e.target.value)} />
                </label>
                <label>
                  Email Address
                  <input required type="email" placeholder="ramesh@rescuenet.in" value={email} onChange={(e) => setEmail(e.target.value)} />
                </label>
              </div>

              <label>
                Operating Area / Ward
                <input required placeholder="e.g. KR Puram, Whitefield" value={area} onChange={(e) => setArea(e.target.value)} />
              </label>

              <label>
                Skills & Certifications
                <input required placeholder="e.g. Swiftwater Swimming, First Aid CPR, Drone Pilot" value={skills} onChange={(e) => setSkills(e.target.value)} />
              </label>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowRegisterModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Registering...' : 'Register Volunteer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
