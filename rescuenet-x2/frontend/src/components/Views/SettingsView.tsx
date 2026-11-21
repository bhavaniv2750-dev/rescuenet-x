import React, { useState, useEffect } from 'react';
import {
  User,
  Bell,
  Monitor,
  Globe,
  ShieldCheck,
  Info,
  CheckCircle2,
  Save,
  RotateCcw,
  Volume2,
  VolumeX,
} from 'lucide-react';

interface SettingsViewProps {
  backendStatus?: string;
  onRefresh?: () => void;
}

interface ProfileState {
  displayName: string;
  email: string;
  callSign: string;
  agency: string;
}

interface NotificationPrefs {
  emergencyPopups: boolean;
  incidentUpdates: boolean;
  browserNotifications: boolean;
  soundAlerts: boolean;
}

interface AppearancePrefs {
  theme: string;
  density: string;
  refreshInterval: string;
}

interface RegionalPrefs {
  region: string;
  units: string;
  timeFormat: string;
}

const DEFAULT_PROFILE: ProfileState = {
  displayName: 'Incident Commander',
  email: 'commander@rescuenet.gov.in',
  callSign: 'BLR-COMMAND-01',
  agency: 'Karnataka State Disaster Management Authority',
};

const DEFAULT_NOTIFICATIONS: NotificationPrefs = {
  emergencyPopups: true,
  incidentUpdates: true,
  browserNotifications: false,
  soundAlerts: false,
};

const DEFAULT_APPEARANCE: AppearancePrefs = {
  theme: 'dark',
  density: 'comfortable',
  refreshInterval: '15',
};

const DEFAULT_REGIONAL: RegionalPrefs = {
  region: 'Bengaluru Urban & Karnataka River Basins',
  units: 'metric',
  timeFormat: '24h',
};

export const SettingsView: React.FC<SettingsViewProps> = () => {
  // Profiles
  const [profile, setProfile] = useState<ProfileState>(() => {
    try {
      const saved = localStorage.getItem('rescuenet_profile');
      return saved ? JSON.parse(saved) : DEFAULT_PROFILE;
    } catch {
      return DEFAULT_PROFILE;
    }
  });

  // Notifications
  const [notifications, setNotifications] = useState<NotificationPrefs>(() => {
    try {
      const saved = localStorage.getItem('rescuenet_notifications');
      return saved ? JSON.parse(saved) : DEFAULT_NOTIFICATIONS;
    } catch {
      return DEFAULT_NOTIFICATIONS;
    }
  });

  // Appearance
  const [appearance, setAppearance] = useState<AppearancePrefs>(() => {
    try {
      const saved = localStorage.getItem('rescuenet_appearance');
      return saved ? JSON.parse(saved) : DEFAULT_APPEARANCE;
    } catch {
      return DEFAULT_APPEARANCE;
    }
  });

  // Regional
  const [regional, setRegional] = useState<RegionalPrefs>(() => {
    try {
      const saved = localStorage.getItem('rescuenet_regional');
      return saved ? JSON.parse(saved) : DEFAULT_REGIONAL;
    } catch {
      return DEFAULT_REGIONAL;
    }
  });

  const [activeSection, setActiveSection] = useState<'profile' | 'notifications' | 'appearance' | 'regional' | 'privacy' | 'about'>('profile');
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Auto-dismiss success message
  useEffect(() => {
    if (feedbackMessage) {
      const timer = setTimeout(() => setFeedbackMessage(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [feedbackMessage]);

  // Request browser notification permission when toggled ON
  const handleToggleBrowserNotifications = async (checked: boolean) => {
    if (checked) {
      if ('Notification' in window) {
        try {
          const perm = await Notification.requestPermission();
          if (perm === 'granted') {
            setNotifications((prev) => ({ ...prev, browserNotifications: true }));
            setFeedbackMessage('Browser notification permission granted.');
          } else {
            setNotifications((prev) => ({ ...prev, browserNotifications: false }));
            setErrorMessage('Browser notification permission was denied in your browser settings.');
          }
        } catch {
          setNotifications((prev) => ({ ...prev, browserNotifications: false }));
        }
      } else {
        setErrorMessage('Desktop notifications are not supported by this browser.');
      }
    } else {
      setNotifications((prev) => ({ ...prev, browserNotifications: false }));
    }
  };

  // Save Handlers
  const handleSaveProfile = (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile.displayName.trim()) {
      setErrorMessage('Display Name cannot be empty.');
      return;
    }
    setErrorMessage(null);
    try {
      localStorage.setItem('rescuenet_profile', JSON.stringify(profile));
      setFeedbackMessage('User profile updated and saved.');
    } catch (err: any) {
      setErrorMessage(`Failed to save profile: ${err.message}`);
    }
  };

  const handleSaveNotifications = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      localStorage.setItem('rescuenet_notifications', JSON.stringify(notifications));
      setFeedbackMessage('Notification preferences updated and saved.');
    } catch (err: any) {
      setErrorMessage(`Failed to save notifications: ${err.message}`);
    }
  };

  const handleSaveAppearance = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      localStorage.setItem('rescuenet_appearance', JSON.stringify(appearance));
      setFeedbackMessage('Display preferences updated and saved.');
    } catch (err: any) {
      setErrorMessage(`Failed to save appearance: ${err.message}`);
    }
  };

  const handleSaveRegional = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      localStorage.setItem('rescuenet_regional', JSON.stringify(regional));
      setFeedbackMessage('Regional preferences updated and saved.');
    } catch (err: any) {
      setErrorMessage(`Failed to save regional settings: ${err.message}`);
    }
  };

  const handleResetAll = () => {
    if (window.confirm('Reset all custom preferences to system defaults?')) {
      localStorage.removeItem('rescuenet_profile');
      localStorage.removeItem('rescuenet_notifications');
      localStorage.removeItem('rescuenet_appearance');
      localStorage.removeItem('rescuenet_regional');
      setProfile(DEFAULT_PROFILE);
      setNotifications(DEFAULT_NOTIFICATIONS);
      setAppearance(DEFAULT_APPEARANCE);
      setRegional(DEFAULT_REGIONAL);
      setFeedbackMessage('All settings have been reset to factory defaults.');
    }
  };

  return (
    <div className="settings-page" style={{ maxWidth: '1080px', margin: '0 auto', paddingBottom: '40px' }}>
      {/* Header */}
      <div className="view-header">
        <div>
          <h2>Settings & Preferences</h2>
          <p>
            Configure operator profile, emergency alert notifications, appearance themes, and regional defaults.
          </p>
        </div>
      </div>

      {/* Global Feedback Banner */}
      {feedbackMessage && (
        <div className="notice-banner banner-success" style={{ marginBottom: '20px' }}>
          <CheckCircle2 size={16} />
          <span>{feedbackMessage}</span>
          <button className="btn-close" onClick={() => setFeedbackMessage(null)}>✕</button>
        </div>
      )}

      {errorMessage && (
        <div className="notice-banner banner-error" style={{ marginBottom: '20px' }}>
          <span>⚠️ {errorMessage}</span>
          <button className="btn-close" onClick={() => setErrorMessage(null)}>✕</button>
        </div>
      )}

      {/* Settings Navigation Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          overflowX: 'auto',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          paddingBottom: '12px',
          marginBottom: '24px',
        }}
      >
        <button
          type="button"
          className={activeSection === 'profile' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '13px', padding: '6px 14px' }}
          onClick={() => setActiveSection('profile')}
        >
          <User size={15} /> Profile
        </button>
        <button
          type="button"
          className={activeSection === 'notifications' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '13px', padding: '6px 14px' }}
          onClick={() => setActiveSection('notifications')}
        >
          <Bell size={15} /> Notifications
        </button>
        <button
          type="button"
          className={activeSection === 'appearance' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '13px', padding: '6px 14px' }}
          onClick={() => setActiveSection('appearance')}
        >
          <Monitor size={15} /> Appearance
        </button>
        <button
          type="button"
          className={activeSection === 'regional' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '13px', padding: '6px 14px' }}
          onClick={() => setActiveSection('regional')}
        >
          <Globe size={15} /> Regional
        </button>
        <button
          type="button"
          className={activeSection === 'privacy' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '13px', padding: '6px 14px' }}
          onClick={() => setActiveSection('privacy')}
        >
          <ShieldCheck size={15} /> Privacy & Security
        </button>
        <button
          type="button"
          className={activeSection === 'about' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '13px', padding: '6px 14px' }}
          onClick={() => setActiveSection('about')}
        >
          <Info size={15} /> About
        </button>
      </div>

      {/* 1. USER PROFILE SECTION */}
      {activeSection === 'profile' && (
        <div className="panel" style={{ maxWidth: '780px' }}>
          <div className="panel-title-bar">
            <div>
              <h3>Operator Profile</h3>
              <p>Personal identification attached to dispatch authorizations and debrief logs</p>
            </div>
            <User size={18} className="text-cyan" />
          </div>

          <form onSubmit={handleSaveProfile} style={{ marginTop: '20px' }}>
            <div className="form-row">
              <label>
                Display Name *
                <input
                  type="text"
                  required
                  value={profile.displayName}
                  onChange={(e) => setProfile({ ...profile, displayName: e.target.value })}
                  placeholder="e.g. Captain A. Sharma"
                />
              </label>

              <label>
                Official Contact Email
                <input
                  type="email"
                  value={profile.email}
                  onChange={(e) => setProfile({ ...profile, email: e.target.value })}
                  placeholder="e.g. ops@rescuenet.gov.in"
                />
              </label>
            </div>

            <div className="form-row">
              <label>
                Call Sign / Station ID
                <input
                  type="text"
                  value={profile.callSign}
                  onChange={(e) => setProfile({ ...profile, callSign: e.target.value })}
                  placeholder="e.g. BLR-COMMAND-01"
                />
              </label>

              <label>
                Agency / Department
                <input
                  type="text"
                  value={profile.agency}
                  onChange={(e) => setProfile({ ...profile, agency: e.target.value })}
                  placeholder="e.g. Karnataka Disaster Management"
                />
              </label>
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
              <button type="submit" className="btn-primary">
                <Save size={15} /> Save Profile Changes
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setProfile(DEFAULT_PROFILE)}
              >
                Reset
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 2. NOTIFICATIONS SECTION */}
      {activeSection === 'notifications' && (
        <div className="panel" style={{ maxWidth: '780px' }}>
          <div className="panel-title-bar">
            <div>
              <h3>Emergency Alerts & Notification Delivery</h3>
              <p>Configure how urgent flood warnings and field updates are presented to the operator</p>
            </div>
            <Bell size={18} className="text-amber" />
          </div>

          <form onSubmit={handleSaveNotifications} style={{ marginTop: '20px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Emergency Popups */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '14px',
                  background: 'rgba(15, 23, 42, 0.6)',
                  borderRadius: '6px',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: '#f8fafc' }}>
                    In-App Emergency Alert Banners
                  </div>
                  <div className="text-xs text-muted" style={{ marginTop: '2px' }}>
                    Show persistent high-visibility warning popups when critical flood emergencies occur.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={notifications.emergencyPopups}
                  onChange={(e) => setNotifications({ ...notifications, emergencyPopups: e.target.checked })}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
              </div>

              {/* Citizen Incidents */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '14px',
                  background: 'rgba(15, 23, 42, 0.6)',
                  borderRadius: '6px',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: '#f8fafc' }}>
                    General Incident Updates
                  </div>
                  <div className="text-xs text-muted" style={{ marginTop: '2px' }}>
                    Refresh and highlight incoming citizen flood intake reports in the navigation badges.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={notifications.incidentUpdates}
                  onChange={(e) => setNotifications({ ...notifications, incidentUpdates: e.target.checked })}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
              </div>

              {/* Desktop Browser Notifications */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '14px',
                  background: 'rgba(15, 23, 42, 0.6)',
                  borderRadius: '6px',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: '#f8fafc' }}>
                    Browser Desktop Notifications
                  </div>
                  <div className="text-xs text-muted" style={{ marginTop: '2px' }}>
                    Receive operating-system notifications when browser tab is running in the background.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={notifications.browserNotifications}
                  onChange={(e) => handleToggleBrowserNotifications(e.target.checked)}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
              </div>

              {/* Audio Alerts */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '14px',
                  background: 'rgba(15, 23, 42, 0.6)',
                  borderRadius: '6px',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  {notifications.soundAlerts ? <Volume2 size={18} className="text-cyan" /> : <VolumeX size={18} className="text-muted" />}
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '14px', color: '#f8fafc' }}>
                      Emergency Audio Chime
                    </div>
                    <div className="text-xs text-muted" style={{ marginTop: '2px' }}>
                      Play an alert chime when a critical life-safety broadcast is received.
                    </div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={notifications.soundAlerts}
                  onChange={(e) => setNotifications({ ...notifications, soundAlerts: e.target.checked })}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
              <button type="submit" className="btn-primary">
                <Save size={15} /> Save Notification Preferences
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 3. APPEARANCE SECTION */}
      {activeSection === 'appearance' && (
        <div className="panel" style={{ maxWidth: '780px' }}>
          <div className="panel-title-bar">
            <div>
              <h3>Display & Theme Preferences</h3>
              <p>Customize dashboard visual styling, interface density, and data polling speed</p>
            </div>
            <Monitor size={18} className="text-emerald" />
          </div>

          <form onSubmit={handleSaveAppearance} style={{ marginTop: '20px' }}>
            <div className="form-row">
              <label>
                Color Theme
                <select
                  value={appearance.theme}
                  onChange={(e) => setAppearance({ ...appearance, theme: e.target.value })}
                >
                  <option value="dark">Tactical Dark (Command Center Standard)</option>
                  <option value="midnight">Deep Midnight (High Contrast Night Mode)</option>
                </select>
              </label>

              <label>
                Layout Density
                <select
                  value={appearance.density}
                  onChange={(e) => setAppearance({ ...appearance, density: e.target.value })}
                >
                  <option value="comfortable">Comfortable (Standard Operations)</option>
                  <option value="compact">Compact (High-Density Multi-Monitor)</option>
                </select>
              </label>
            </div>

            <div className="form-row">
              <label>
                Live Telemetry Polling Rate
                <select
                  value={appearance.refreshInterval}
                  onChange={(e) => setAppearance({ ...appearance, refreshInterval: e.target.value })}
                >
                  <option value="15">Every 15 Seconds (Real-Time Disaster Ops)</option>
                  <option value="30">Every 30 Seconds (Balanced Telemetry)</option>
                  <option value="60">Every 60 Seconds (Low Network Bandwidth)</option>
                </select>
              </label>
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
              <button type="submit" className="btn-primary">
                <Save size={15} /> Apply Display Settings
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 4. REGIONAL SECTION */}
      {activeSection === 'regional' && (
        <div className="panel" style={{ maxWidth: '780px' }}>
          <div className="panel-title-bar">
            <div>
              <h3>Regional Jurisdiction & Units</h3>
              <p>Geographic monitoring boundaries and operational measurement standards</p>
            </div>
            <Globe size={18} className="text-cyan" />
          </div>

          <form onSubmit={handleSaveRegional} style={{ marginTop: '20px' }}>
            <div className="form-row">
              <label>
                Primary Operational Jurisdiction
                <input
                  type="text"
                  disabled
                  value={regional.region}
                  style={{ opacity: 0.8, cursor: 'not-allowed' }}
                />
                <span className="text-xs text-muted" style={{ marginTop: '4px', display: 'block' }}>
                  Targeted to Karnataka river basins (Cauvery, Shimsha, Biligundulu) and Bengaluru urban corridors.
                </span>
              </label>
            </div>

            <div className="form-row">
              <label>
                Hydrological & Distance Units
                <select
                  value={regional.units}
                  onChange={(e) => setRegional({ ...regional, units: e.target.value })}
                >
                  <option value="metric">Metric Standards (Kilometers, Meters Depth, mm/hr Rainfall)</option>
                </select>
              </label>

              <label>
                Time Display Format
                <select
                  value={regional.timeFormat}
                  onChange={(e) => setRegional({ ...regional, timeFormat: e.target.value })}
                >
                  <option value="24h">24-Hour Military Format (14:30:00 IST)</option>
                  <option value="12h">12-Hour Standard Format (02:30:00 PM IST)</option>
                </select>
              </label>
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
              <button type="submit" className="btn-primary">
                <Save size={15} /> Save Regional Preferences
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 5. PRIVACY & SECURITY SECTION */}
      {activeSection === 'privacy' && (
        <div className="panel" style={{ maxWidth: '780px' }}>
          <div className="panel-title-bar">
            <div>
              <h3>Privacy & Local Storage Integrity</h3>
              <p>Platform data handling standards and local workstation cache controls</p>
            </div>
            <ShieldCheck size={18} className="text-emerald" />
          </div>

          <div style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div
              style={{
                padding: '16px',
                background: 'rgba(15, 23, 42, 0.6)',
                borderRadius: '6px',
                border: '1px solid rgba(255, 255, 255, 0.06)',
                lineHeight: '1.6',
                fontSize: '13px',
                color: '#cbd5e1',
              }}
            >
              <h4 style={{ color: '#f8fafc', marginBottom: '6px' }}>Local-First Operations Policy</h4>
              <p>
                RescueNet X 2.0 operates strictly in a local-first architecture. All incident reports,
                photographic attachments, telemetry logs, and mission debrief records are persisted directly
                into your workstation's secure local database. No user data, field coordinates, or survivor
                information is transmitted to third-party advertising or commercial tracking services.
              </p>
            </div>

            <div
              style={{
                padding: '16px',
                background: 'rgba(15, 23, 42, 0.6)',
                borderRadius: '6px',
                border: '1px solid rgba(255, 255, 255, 0.06)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <div style={{ fontWeight: 600, fontSize: '14px', color: '#f8fafc' }}>
                  Reset Workstation Preferences
                </div>
                <div className="text-xs text-muted" style={{ marginTop: '2px' }}>
                  Clears all custom saved profiles, notification choices, and display settings from browser storage.
                </div>
              </div>
              <button
                type="button"
                className="btn-secondary"
                style={{ color: '#ef4444', borderColor: '#ef4444' }}
                onClick={handleResetAll}
              >
                <RotateCcw size={14} /> Reset Defaults
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. ABOUT SECTION */}
      {activeSection === 'about' && (
        <div className="panel" style={{ maxWidth: '780px' }}>
          <div className="panel-title-bar">
            <div>
              <h3>About the System</h3>
              <p>RescueNet X 2.0 Platform Overview</p>
            </div>
            <Info size={18} className="text-cyan" />
          </div>

          <div style={{ marginTop: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <div
                style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #0284c7 0%, #06b6d4 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#fff',
                  fontWeight: 'bold',
                  fontSize: '18px',
                }}
              >
                RX
              </div>
              <div>
                <div style={{ fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>
                  Flood Digital Twin + RescueNet X 2.0
                </div>
                <div className="text-xs text-muted">
                  AI-Powered Autonomous Disaster Intelligence & Emergency Response Platform
                </div>
              </div>
            </div>

            <p style={{ fontSize: '13px', lineHeight: '1.6', color: '#94a3b8', marginBottom: '20px' }}>
              RescueNet X combines geospatial river basin catchment models, river gauge threshold monitoring,
              predictive flood forecasting, and coordinated multi-agency rescue dispatch. Built to deliver
              rapid situational awareness during extreme monsoon events and urban inundation crises.
            </p>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: '12px',
                borderTop: '1px solid rgba(255, 255, 255, 0.08)',
                paddingTop: '16px',
              }}
            >
              <div className="stat-card" style={{ padding: '12px' }}>
                <span className="stat-label">Software Version</span>
                <span className="stat-value font-mono" style={{ fontSize: '15px' }}>v2.0.0</span>
              </div>

              <div className="stat-card" style={{ padding: '12px' }}>
                <span className="stat-label">System Architecture</span>
                <span className="stat-value font-mono" style={{ fontSize: '15px' }}>FastAPI + React 18</span>
              </div>

              <div className="stat-card" style={{ padding: '12px' }}>
                <span className="stat-label">Geographic Coverage</span>
                <span className="stat-value" style={{ fontSize: '13px' }}>Karnataka River Basins</span>
              </div>

              <div className="stat-card" style={{ padding: '12px' }}>
                <span className="stat-label">Operational Mode</span>
                <span className="stat-value text-emerald" style={{ fontSize: '13px' }}>Local Air-Gapped Console</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
