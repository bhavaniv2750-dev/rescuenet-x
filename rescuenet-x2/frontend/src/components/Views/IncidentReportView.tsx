import React, { useState, useEffect } from 'react';
import { api } from '../../api/client';
import type { Incident } from '../../api/types';
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Clock,
  Eye,
  FilePlus,
  Image as ImageIcon,
  MapPin,
  Phone,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  User,
  Users,
} from 'lucide-react';

interface IncidentReportViewProps {
  onSuccess: () => void;
}

const PRESET_LOCATIONS = [
  { name: 'KR Puram Lowlands', lat: 13.007, lng: 77.696 },
  { name: 'Bellandur Lake Basin', lat: 12.9352, lng: 77.6778 },
  { name: 'Outer Ring Road (Ecospace)', lat: 12.9258, lng: 77.6844 },
  { name: 'HSR Layout Sector 6', lat: 12.9116, lng: 77.6389 },
  { name: 'Hebbal Flyover Drain', lat: 13.0358, lng: 77.597 },
];

export const IncidentReportView: React.FC<IncidentReportViewProps> = ({ onSuccess }) => {
  const [activeTab, setActiveTab] = useState<'form' | 'directory'>('form');

  // Form State
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [area, setArea] = useState('KR Puram Lowlands, Bengaluru');
  const [incidentType, setIncidentType] = useState('FLASH_FLOOD');
  const [severity, setSeverity] = useState('HIGH');
  const [peopleAffected, setPeopleAffected] = useState(4);
  const [latitude, setLatitude] = useState(13.007);
  const [longitude, setLongitude] = useState(77.696);
  const [reporterName, setReporterName] = useState('');
  const [reporterContact, setReporterContact] = useState('');

  // Image Upload State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [uploadedImageUrl, setUploadedImageUrl] = useState<string | null>(null);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Submission State
  const [submitting, setSubmitting] = useState(false);
  const [submittedNotice, setSubmittedNotice] = useState<string | null>(null);

  // Directory State
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [loadingDirectory, setLoadingDirectory] = useState(false);

  const fetchIncidents = async () => {
    setLoadingDirectory(true);
    try {
      const res = await api.getIncidents({
        search: searchQuery || undefined,
        status: statusFilter !== 'ALL' ? statusFilter : undefined,
      });
      setIncidents(res.items);
      if (res.items.length > 0 && !selectedIncident) {
        setSelectedIncident(res.items[0]);
      }
    } catch (err: any) {
      console.error('Error fetching incidents:', err);
    } finally {
      setLoadingDirectory(false);
    }
  };

  useEffect(() => {
    fetchIncidents();
  }, [searchQuery, statusFilter]);

  // Handle local file selection and immediate backend upload
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate size (10 MB limit)
    if (file.size > 10 * 1024 * 1024) {
      setUploadError('File size exceeds the 10MB limit.');
      return;
    }

    // Validate type
    if (!file.type.startsWith('image/')) {
      setUploadError('Please select a valid image file (PNG, JPG, WEBP, GIF).');
      return;
    }

    setUploadError(null);
    setSelectedFile(file);

    // Create local object URL for instant preview
    const previewUrl = URL.createObjectURL(file);
    setImagePreview(previewUrl);

    // Upload to backend storage
    setUploadingImage(true);
    try {
      const uploadRes = await api.uploadIncidentImage(file);
      setUploadedImageUrl(uploadRes.image_url);
    } catch (err: any) {
      setUploadError(err.message || 'Image upload failed. Please try again.');
    } finally {
      setUploadingImage(false);
    }
  };

  const handleRemoveImage = () => {
    setSelectedFile(null);
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview);
      setImagePreview(null);
    }
    setUploadedImageUrl(null);
    setUploadError(null);
  };

  const handlePresetSelect = (preset: typeof PRESET_LOCATIONS[0]) => {
    setArea(`${preset.name}, Bengaluru`);
    setLatitude(preset.lat);
    setLongitude(preset.lng);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmittedNotice(null);

    try {
      const newInc = await api.createIncident({
        title,
        description,
        area,
        severity,
        people_affected: peopleAffected,
        latitude,
        longitude,
        source: 'CITIZEN_REPORT',
        incident_type: incidentType,
        image_url: uploadedImageUrl,
        reporter_name: reporterName || undefined,
        reporter_contact: reporterContact || undefined,
      });

      setSubmittedNotice(
        `Incident ${newInc.id} registered and persisted to database. Queued for responder triage.`
      );
      setTitle('');
      setDescription('');
      setReporterName('');
      setReporterContact('');
      handleRemoveImage();

      // Refresh data
      onSuccess();
      await fetchIncidents();
      setSelectedIncident(newInc);
      setActiveTab('directory');
    } catch (err: any) {
      alert(`Submission error: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleStatusUpdate = async (incidentId: string, newStatus: string) => {
    try {
      const updated = await api.updateIncident(incidentId, { status: newStatus });
      setSelectedIncident(updated);
      setIncidents((prev) => prev.map((inc) => (inc.id === incidentId ? updated : inc)));
      onSuccess();
    } catch (err: any) {
      alert(`Status update failed: ${err.message}`);
    }
  };

  const resolveImageSource = (url?: string | null) => {
    if (!url) return null;
    if (url.startsWith('http://') || url.startsWith('https://')) return url;
    return `http://127.0.0.1:8000${url}`;
  };

  return (
    <div className="incident-management-container" style={{ maxWidth: '1200px', margin: '0 auto' }}>
      {/* View Header */}
      <div className="view-header">
        <div>
          <h2>Incident Reporting, Triage & Verification</h2>
          <p>
            Ground-truth emergency intake portal. Citizen reports are validated, geotagged, linked to
            field photographic evidence, and routed to rescue command.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className={activeTab === 'form' ? 'btn-primary' : 'btn-secondary'}
            onClick={() => setActiveTab('form')}
          >
            <FilePlus size={16} /> New Incident Intake
          </button>
          <button
            className={activeTab === 'directory' ? 'btn-primary' : 'btn-secondary'}
            onClick={() => setActiveTab('directory')}
          >
            <Eye size={16} /> Incident Directory ({incidents.length})
          </button>
        </div>
      </div>

      {submittedNotice && (
        <div className="notice-banner banner-success" style={{ marginBottom: '16px' }}>
          <CheckCircle2 size={18} />
          <span>{submittedNotice}</span>
          <button className="btn-close" onClick={() => setSubmittedNotice(null)}>✕</button>
        </div>
      )}

      {/* TAB 1: FORM */}
      {activeTab === 'form' && (
        <div className="panel form-panel" style={{ maxWidth: '850px', margin: '0 auto' }}>
          <div className="panel-title-bar">
            <div>
              <h3>Emergency Incident Intake Form</h3>
              <p>Enter ground-truth field observations and attach photographic evidence</p>
            </div>
            <AlertTriangle size={18} className="text-amber" />
          </div>

          <form onSubmit={handleSubmit} className="incident-intake-form" style={{ marginTop: '16px' }}>
            <label>
              Incident Headline / Emergency Summary *
              <input
                required
                minLength={5}
                placeholder="e.g. Ground Floor Inundated, 4 Trapped near Devasandra Lake Outlet"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>

            <div className="form-row">
              <label>
                Incident Category *
                <select value={incidentType} onChange={(e) => setIncidentType(e.target.value)}>
                  <option value="FLASH_FLOOD">Flash Flooding / Torrential Runoff</option>
                  <option value="LAKE_OVERFLOW">Lake / Canal Breach & Overflow</option>
                  <option value="TRAPPED_CIVILIANS">Trapped Civilians / Roof Stranding</option>
                  <option value="UNDERPASS_SUBMERGED">Underpass / Roadway Submerged</option>
                  <option value="INFRASTRUCTURE_FAILURE">Power Substation / Wall Collapse</option>
                  <option value="CONTAMINATION">Water Contamination / Hazard Spill</option>
                </select>
              </label>

              <label>
                Assessed Severity *
                <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                  <option value="CRITICAL">CRITICAL — Life-Threatening (Water &gt; 1.5m / Trapped)</option>
                  <option value="HIGH">HIGH — Residential Inundation / Power Cut</option>
                  <option value="MODERATE">MODERATE — Road Cut-off / Vehicle Stranded</option>
                  <option value="LOW">LOW — Minor Waterlogging / Monitoring</option>
                </select>
              </label>
            </div>

            <label>
              Locality / Neighborhood Landmark *
              <input
                required
                placeholder="e.g. KR Puram, Near Rainbow Drive, Outer Ring Road"
                value={area}
                onChange={(e) => setArea(e.target.value)}
              />
            </label>

            {/* Quick Presets */}
            <div style={{ marginBottom: '14px' }}>
              <span className="text-xs text-muted" style={{ marginRight: '8px' }}>
                Quick Geolocation Presets:
              </span>
              <div style={{ display: 'inline-flex', gap: '6px', flexWrap: 'wrap' }}>
                {PRESET_LOCATIONS.map((p) => (
                  <button
                    key={p.name}
                    type="button"
                    className="btn-secondary"
                    style={{ fontSize: '11px', padding: '2px 8px' }}
                    onClick={() => handlePresetSelect(p)}
                  >
                    📍 {p.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-row">
              <label>
                GPS Latitude *
                <input
                  type="number"
                  step="0.0001"
                  required
                  value={latitude}
                  onChange={(e) => setLatitude(parseFloat(e.target.value))}
                />
              </label>

              <label>
                GPS Longitude *
                <input
                  type="number"
                  step="0.0001"
                  required
                  value={longitude}
                  onChange={(e) => setLongitude(parseFloat(e.target.value))}
                />
              </label>
            </div>

            <div className="form-row">
              <label>
                Estimated People Affected / Trapped *
                <input
                  type="number"
                  min={1}
                  max={5000}
                  required
                  value={peopleAffected}
                  onChange={(e) => setPeopleAffected(parseInt(e.target.value) || 1)}
                />
              </label>

              <label>
                Reporter Name (Optional)
                <input
                  placeholder="Citizen / Community Ward Officer"
                  value={reporterName}
                  onChange={(e) => setReporterName(e.target.value)}
                />
              </label>

              <label>
                Reporter Contact Phone (Optional)
                <input
                  placeholder="+91-98765-43210"
                  value={reporterContact}
                  onChange={(e) => setReporterContact(e.target.value)}
                />
              </label>
            </div>

            <label>
              Detailed Field Observations *
              <textarea
                required
                rows={4}
                minLength={10}
                placeholder="Include estimated water height, presence of elderly or infants, immediate obstacles (downed cables, swift current, blocked gates)..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>

            {/* Photographic Evidence Attachment */}
            <div
              className="image-upload-section"
              style={{
                border: '1px dashed #334155',
                borderRadius: '8px',
                padding: '16px',
                background: 'rgba(15, 23, 42, 0.6)',
                marginBottom: '16px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Camera size={18} className="text-cyan" />
                  <strong>Attach Photographic Disaster Observation</strong>
                </div>
                <span className="text-xs text-muted">JPG, PNG, WEBP (Max 10MB)</span>
              </div>

              {!imagePreview ? (
                <div>
                  <input
                    type="file"
                    id="incident-file-input"
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    style={{ display: 'none' }}
                    onChange={handleFileChange}
                  />
                  <label
                    htmlFor="incident-file-input"
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      padding: '24px',
                      cursor: 'pointer',
                      border: '1px solid #1e293b',
                      borderRadius: '6px',
                      background: 'rgba(30, 41, 59, 0.4)',
                    }}
                  >
                    <Upload size={24} className="text-muted" style={{ marginBottom: '8px' }} />
                    <span style={{ fontSize: '13px', fontWeight: 600 }}>Click to browse or upload disaster photo</span>
                    <span className="text-xs text-muted" style={{ marginTop: '4px' }}>
                      Image will be uploaded to backend storage and linked to the incident record
                    </span>
                  </label>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                  <div
                    style={{
                      width: '120px',
                      height: '80px',
                      borderRadius: '6px',
                      overflow: 'hidden',
                      border: '1px solid #38bdf8',
                      position: 'relative',
                    }}
                  >
                    <img
                      src={imagePreview}
                      alt="Selected Preview"
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    />
                  </div>

                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '13px', fontWeight: 600 }}>
                      {selectedFile?.name || 'Uploaded Photo'}
                    </div>
                    <div className="text-xs text-muted">
                      {selectedFile ? `${(selectedFile.size / 1024).toFixed(1)} KB` : ''}
                    </div>
                    {uploadingImage && (
                      <div className="text-xs text-cyan" style={{ marginTop: '4px' }}>
                        Uploading to backend server...
                      </div>
                    )}
                    {uploadedImageUrl && (
                      <div className="text-xs text-emerald" style={{ marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <CheckCircle2 size={12} /> Stored on server: <code>{uploadedImageUrl}</code>
                      </div>
                    )}
                  </div>

                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ color: '#ef4444', borderColor: '#ef4444' }}
                    onClick={handleRemoveImage}
                  >
                    <Trash2 size={14} /> Remove
                  </button>
                </div>
              )}

              {uploadError && (
                <div className="text-xs text-rose" style={{ marginTop: '8px' }}>
                  ⚠️ {uploadError}
                </div>
              )}
            </div>

            <button
              type="submit"
              className="btn-primary btn-block"
              disabled={submitting || uploadingImage}
              style={{ padding: '12px', fontSize: '14px', fontWeight: 600 }}
            >
              {submitting
                ? 'Validating & Persisting Incident...'
                : uploadingImage
                ? 'Uploading Image Attachment...'
                : 'Transmit Incident Report to Dispatch'}
            </button>
          </form>
        </div>
      )}

      {/* TAB 2: DIRECTORY & DETAIL VIEW */}
      {activeTab === 'directory' && (
        <div style={{ display: 'grid', gridTemplateColumns: '400px 1fr', gap: '20px' }}>
          {/* Left Column: Filter & List */}
          <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '700px' }}>
            <div style={{ marginBottom: '12px' }}>
              <div style={{ position: 'relative', marginBottom: '8px' }}>
                <Search size={14} style={{ position: 'absolute', left: '10px', top: '10px', color: '#64748b' }} />
                <input
                  type="text"
                  placeholder="Search incidents by ID, title, or area..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{ width: '100%', paddingLeft: '32px', fontSize: '13px' }}
                />
              </div>

              {/* Status Filter */}
              <div style={{ display: 'flex', gap: '4px', overflowX: 'auto', paddingBottom: '4px' }}>
                {['ALL', 'REPORTED', 'VERIFIED', 'ASSIGNED', 'RESOLVED'].map((st) => (
                  <button
                    key={st}
                    className={`status-pill ${statusFilter === st ? 'pill-active' : ''}`}
                    style={{ cursor: 'pointer', fontSize: '11px', padding: '2px 8px' }}
                    onClick={() => setStatusFilter(st)}
                  >
                    {st}
                  </button>
                ))}
              </div>
            </div>

            {/* List */}
            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {loadingDirectory ? (
                <div className="text-center text-muted" style={{ padding: '24px' }}>
                  Loading database records...
                </div>
              ) : incidents.length === 0 ? (
                <div className="text-center text-muted" style={{ padding: '24px' }}>
                  No matching incidents found.
                </div>
              ) : (
                incidents.map((inc) => {
                  const isSelected = selectedIncident?.id === inc.id;
                  const isCitizen = inc.source === 'CITIZEN_REPORT';
                  return (
                    <div
                      key={inc.id}
                      onClick={() => setSelectedIncident(inc)}
                      style={{
                        padding: '12px',
                        borderRadius: '6px',
                        background: isSelected ? 'rgba(8, 145, 178, 0.15)' : 'rgba(15, 23, 42, 0.6)',
                        border: isSelected ? '1px solid #0891b2' : '1px solid rgba(255, 255, 255, 0.05)',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <span className="font-mono font-bold text-xs" style={{ color: '#38bdf8' }}>
                          {inc.id}
                        </span>
                        <span
                          className={`status-pill ${
                            inc.status === 'REPORTED'
                              ? 'pill-amber'
                              : inc.status === 'VERIFIED'
                              ? 'pill-cyan'
                              : inc.status === 'RESOLVED'
                              ? 'pill-muted'
                              : 'pill-active'
                          }`}
                          style={{ fontSize: '10px' }}
                        >
                          {inc.status}
                        </span>
                      </div>

                      <div style={{ fontSize: '13px', fontWeight: 600, color: '#f1f5f9', marginBottom: '4px' }}>
                        {inc.title}
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#94a3b8' }}>
                        <span>📍 {inc.area}</span>
                        <span style={{ color: inc.severity === 'CRITICAL' ? '#ef4444' : '#f59e0b' }}>
                          {inc.severity}
                        </span>
                      </div>

                      <div style={{ display: 'flex', gap: '8px', marginTop: '6px', alignItems: 'center', fontSize: '10px', color: '#64748b' }}>
                        <span>{isCitizen ? '👤 Citizen Report' : '📡 MESH Telemetry'}</span>
                        {inc.image_url && <span style={{ color: '#06b6d4' }}>📷 Photo Attached</span>}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Column: Selected Incident Detail */}
          <div className="panel" style={{ height: '700px', overflowY: 'auto' }}>
            {selectedIncident ? (
              <div>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #1e293b', paddingBottom: '16px', marginBottom: '16px' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                      <span className="code-badge font-mono font-bold" style={{ fontSize: '13px' }}>
                        {selectedIncident.id}
                      </span>
                      <span
                        className={`status-pill ${
                          selectedIncident.status === 'REPORTED'
                            ? 'pill-amber'
                            : selectedIncident.status === 'VERIFIED'
                            ? 'pill-cyan'
                            : selectedIncident.status === 'RESOLVED'
                            ? 'pill-muted'
                            : 'pill-active'
                        }`}
                      >
                        {selectedIncident.status}
                      </span>
                      <span
                        className="status-pill"
                        style={{
                          background: selectedIncident.severity === 'CRITICAL' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                          color: selectedIncident.severity === 'CRITICAL' ? '#ef4444' : '#f59e0b',
                        }}
                      >
                        {selectedIncident.severity}
                      </span>
                    </div>
                    <h3 style={{ margin: 0, fontSize: '18px', color: '#f8fafc' }}>
                      {selectedIncident.title}
                    </h3>
                  </div>

                  {/* Status Actions */}
                  <div style={{ display: 'flex', gap: '6px' }}>
                    {selectedIncident.status === 'REPORTED' && (
                      <button
                        className="btn-primary"
                        style={{ fontSize: '12px' }}
                        onClick={() => handleStatusUpdate(selectedIncident.id, 'VERIFIED')}
                      >
                        <ShieldCheck size={14} /> Verify Incident
                      </button>
                    )}
                    {selectedIncident.status !== 'RESOLVED' && (
                      <button
                        className="btn-secondary"
                        style={{ fontSize: '12px', color: '#10b981', borderColor: '#10b981' }}
                        onClick={() => handleStatusUpdate(selectedIncident.id, 'RESOLVED')}
                      >
                        Mark Resolved
                      </button>
                    )}
                  </div>
                </div>

                {/* Details Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px', marginBottom: '20px' }}>
                  <div className="stat-card">
                    <span className="stat-label">Location / Area</span>
                    <span className="stat-value" style={{ fontSize: '14px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <MapPin size={14} className="text-cyan" /> {selectedIncident.area}
                    </span>
                    <span className="text-xs text-muted" style={{ marginTop: '4px' }}>
                      Lat: {selectedIncident.latitude.toFixed(4)}, Lng: {selectedIncident.longitude.toFixed(4)}
                    </span>
                  </div>

                  <div className="stat-card">
                    <span className="stat-label">People Requiring Rescue</span>
                    <span className="stat-value" style={{ fontSize: '16px', color: '#ef4444', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Users size={16} /> {selectedIncident.people_affected} Civilians
                    </span>
                    <span className="text-xs text-muted" style={{ marginTop: '4px' }}>
                      Source: {selectedIncident.source}
                    </span>
                  </div>

                  <div className="stat-card">
                    <span className="stat-label">Reporter Information</span>
                    <span className="stat-value" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <User size={14} className="text-muted" /> {selectedIncident.reporter_name || 'Anonymous Citizen'}
                    </span>
                    <span className="text-xs text-muted" style={{ marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Phone size={12} /> {selectedIncident.reporter_contact || 'No phone provided'}
                    </span>
                  </div>

                  <div className="stat-card">
                    <span className="stat-label">Intake Timestamp</span>
                    <span className="stat-value" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={14} className="text-muted" /> {new Date(selectedIncident.created_at).toLocaleString()}
                    </span>
                    <span className="text-xs text-muted" style={{ marginTop: '4px' }}>
                      Assigned Team: {selectedIncident.assigned_team_id || 'Pending Dispatch'}
                    </span>
                  </div>
                </div>

                {/* Description */}
                <div style={{ marginBottom: '20px' }}>
                  <h4 style={{ fontSize: '13px', color: '#94a3b8', textTransform: 'uppercase', marginBottom: '8px' }}>
                    Field Situation Report
                  </h4>
                  <div
                    style={{
                      background: 'rgba(15, 23, 42, 0.7)',
                      padding: '14px',
                      borderRadius: '6px',
                      fontSize: '13px',
                      lineHeight: '1.6',
                      color: '#cbd5e1',
                      border: '1px solid rgba(255, 255, 255, 0.05)',
                    }}
                  >
                    {selectedIncident.description}
                  </div>
                </div>

                {/* Attached Photographic Evidence */}
                <div>
                  <h4 style={{ fontSize: '13px', color: '#94a3b8', textTransform: 'uppercase', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <ImageIcon size={14} /> Photographic Field Evidence
                  </h4>
                  {selectedIncident.image_url ? (
                    <div
                      style={{
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: '1px solid #334155',
                        background: '#020617',
                        maxHeight: '360px',
                        display: 'flex',
                        justifyContent: 'center',
                        alignItems: 'center',
                      }}
                    >
                      <img
                        src={resolveImageSource(selectedIncident.image_url) || ''}
                        alt={`Observation for ${selectedIncident.id}`}
                        style={{ maxWidth: '100%', maxHeight: '360px', objectFit: 'contain' }}
                        onError={(e) => {
                          (e.target as any).src = 'https://images.unsplash.com/photo-1547683905-f686c993aae5?auto=format&fit=crop&w=600&q=80';
                        }}
                      />
                    </div>
                  ) : (
                    <div
                      style={{
                        padding: '24px',
                        borderRadius: '6px',
                        background: 'rgba(15, 23, 42, 0.4)',
                        border: '1px dashed #334155',
                        textAlign: 'center',
                        color: '#64748b',
                        fontSize: '13px',
                      }}
                    >
                      No photographic attachment recorded with this intake report.
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center text-muted" style={{ padding: '60px' }}>
                Select an incident from the directory to review its details and evidence.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
