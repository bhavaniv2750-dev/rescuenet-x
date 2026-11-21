import { useState, useEffect, useCallback } from 'react';
import './index.css';
import { api } from './api/client';
import type {
  Alert,
  DashboardData,
  Facility,
  Incident,
  RescueTeam,
  RiverGauge,
  Volunteer,
} from './api/types';
import { Sidebar } from './components/Layout/Sidebar';
import { Topbar } from './components/Layout/Topbar';
import { OverviewView } from './components/Views/OverviewView';
import { DigitalTwinView } from './components/Views/DigitalTwinView';
import { ForecastingView } from './components/Views/ForecastingView';
import { AlertsView } from './components/Views/AlertsView';
import { RescueOperationsView } from './components/Views/RescueOperationsView';
import { VolunteersView } from './components/Views/VolunteersView';
import { FacilitiesView } from './components/Views/FacilitiesView';
import { IncidentReportView } from './components/Views/IncidentReportView';
import { RescueRecordsView } from './components/Views/RescueRecordsView';
import { SupervisorView } from './components/Views/SupervisorView';
import { DatasetsView } from './components/Views/DatasetsView';
import { SettingsView } from './components/Views/SettingsView';

export function App() {
  const [activePage, setActivePage] = useState<string>('Overview');
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);
  const [backendStatus, setBackendStatus] = useState<string>('Checking...');
  const [refreshing, setRefreshing] = useState<boolean>(false);

  // Core Data Stores
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [teams, setTeams] = useState<RescueTeam[]>([]);
  const [volunteers, setVolunteers] = useState<Volunteer[]>([]);
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [gauges, setGauges] = useState<RiverGauge[]>([]);
  const [catchmentsGeoJSON, setCatchmentsGeoJSON] = useState<any>(null);

  // Quick Report Modal
  const [showReportModal, setShowReportModal] = useState<boolean>(false);

  const loadAllData = useCallback(async () => {
    setRefreshing(true);
    try {
      // 1. Health check
      await api.checkHealth();
      setBackendStatus('Connected');

      // 2. Fetch parallel data
      const [
        dash,
        incRes,
        altRes,
        teamRes,
        volRes,
        facRes,
        gaugeRes,
        catchRes,
      ] = await Promise.allSettled([
        api.getDashboard(),
        api.getIncidents(),
        api.getAlerts(),
        api.getTeams(),
        api.getVolunteers(),
        api.getFacilities(),
        api.getRiverGauges(),
        api.getCatchmentsGeoJSON(),
      ]);

      if (dash.status === 'fulfilled') setDashboardData(dash.value);
      if (incRes.status === 'fulfilled') setIncidents(incRes.value.items);
      if (altRes.status === 'fulfilled') setAlerts(altRes.value.items);
      if (teamRes.status === 'fulfilled') setTeams(teamRes.value.items);
      if (volRes.status === 'fulfilled') setVolunteers(volRes.value.items);
      if (facRes.status === 'fulfilled') setFacilities(facRes.value.items);
      if (gaugeRes.status === 'fulfilled') setGauges(gaugeRes.value.items);
      if (catchRes.status === 'fulfilled') setCatchmentsGeoJSON(catchRes.value);
    } catch (err) {
      console.error('Backend connection error:', err);
      setBackendStatus('Offline');
    } finally {
      setRefreshing(false);
    }
  }, []);

  // Persistent dismissed alert tracking to avoid duplicate popups
  const [dismissedAlertIds, setDismissedAlertIds] = useState<Set<string>>(new Set());

  // Initial load and periodic polling
  useEffect(() => {
    loadAllData();
    const interval = setInterval(loadAllData, 15000);
    return () => clearInterval(interval);
  }, [loadAllData]);

  const activeAlertsCount = alerts.filter((a) => a.status === 'ACTIVE').length;
  const activeIncidentsCount = incidents.filter((i) => i.status !== 'RESOLVED').length;

  // Newest qualifying high/critical emergency alert that has not been dismissed in this session
  const newestEmergencyAlert = alerts.find(
    (a) =>
      a.status === 'ACTIVE' &&
      (a.severity === 'CRITICAL' || a.severity === 'HIGH') &&
      !dismissedAlertIds.has(a.id)
  );

  // Optional non-blocking browser notification
  useEffect(() => {
    if (
      newestEmergencyAlert &&
      typeof window !== 'undefined' &&
      'Notification' in window &&
      Notification.permission === 'granted'
    ) {
      try {
        new Notification(`[${newestEmergencyAlert.severity}] ${newestEmergencyAlert.title}`, {
          body: `${newestEmergencyAlert.area}: ${newestEmergencyAlert.message}`,
        });
      } catch {}
    }
  }, [newestEmergencyAlert?.id]);

  return (
    <div className="app-shell">
      {/* Sidebar Navigation */}
      <Sidebar
        activePage={activePage}
        onNavigate={(page) => setActivePage(page)}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        backendStatus={backendStatus}
        incidentCount={activeIncidentsCount}
        activeAlertCount={activeAlertsCount}
      />

      {/* Main Content Area */}
      <div className="app-main">
        <Topbar
          activePage={activePage}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          onRefresh={loadAllData}
          onOpenReportModal={() => setShowReportModal(true)}
          refreshing={refreshing}
        />

        <main className="page-viewport">
          {activePage === 'Overview' && (
            <OverviewView
              data={dashboardData}
              loading={refreshing && !dashboardData}
              onNavigate={(page) => setActivePage(page)}
              onSelectIncident={() => setActivePage('Rescue Operations')}
              catchmentsGeoJSON={catchmentsGeoJSON}
              incidents={incidents}
              alerts={alerts}
              teams={teams}
              facilities={facilities}
              gauges={gauges}
            />
          )}

          {activePage === 'Flood Digital Twin' && (
            <DigitalTwinView
              catchmentsGeoJSON={catchmentsGeoJSON}
              incidents={incidents}
              teams={teams}
              facilities={facilities}
              gauges={gauges}
              alerts={alerts}
            />
          )}

          {activePage === 'Flood Forecasting' && (
            <ForecastingView initialForecast={dashboardData?.forecast_preview} />
          )}

          {activePage === 'Emergency Alerts' && (
            <AlertsView alerts={alerts} onRefresh={loadAllData} />
          )}

          {activePage === 'Rescue Operations' && (
            <RescueOperationsView
              incidents={incidents}
              teams={teams}
              onRefresh={loadAllData}
              onOpenReportModal={() => setShowReportModal(true)}
            />
          )}

          {activePage === 'Volunteer Coordination' && (
            <VolunteersView volunteers={volunteers} onRefresh={loadAllData} />
          )}

          {activePage === 'Facilities & Shelters' && (
            <FacilitiesView facilities={facilities} onRefresh={loadAllData} />
          )}

          {activePage === 'Incident Reports' && (
            <IncidentReportView
              onSuccess={() => {
                loadAllData();
                setActivePage('Rescue Operations');
              }}
            />
          )}

          {activePage === 'Rescue Records' && <RescueRecordsView />}

          {activePage === 'AI Supervisor' && <SupervisorView incidents={incidents} />}

          {activePage === 'Data & Models' && <DatasetsView />}

          {activePage === 'Settings' && (
            <SettingsView backendStatus={backendStatus} onRefresh={loadAllData} />
          )}
        </main>
      </div>

      {/* In-App Emergency Alert Notification Popup (Mounted at Application Shell Level) */}
      {newestEmergencyAlert && (
        <div
          role="alert"
          aria-live="assertive"
          className="emergency-toast-banner"
          style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            maxWidth: '450px',
            zIndex: 9999,
            background:
              newestEmergencyAlert.severity === 'CRITICAL'
                ? 'rgba(69, 10, 10, 0.96)'
                : 'rgba(67, 20, 7, 0.96)',
            backdropFilter: 'blur(12px)',
            border: `1px solid ${
              newestEmergencyAlert.severity === 'CRITICAL' ? '#ef4444' : '#f97316'
            }`,
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.7), 0 0 16px rgba(239, 68, 68, 0.3)',
            borderRadius: '8px',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  background:
                    newestEmergencyAlert.severity === 'CRITICAL' ? '#dc2626' : '#ea580c',
                  color: '#ffffff',
                  fontSize: '11px',
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: '4px',
                  letterSpacing: '0.05em',
                }}
              >
                {newestEmergencyAlert.severity} ALERT
              </span>
              <span className="font-mono text-xs text-muted">{newestEmergencyAlert.id}</span>
            </div>
            <button
              type="button"
              onClick={() => {
                setDismissedAlertIds((prev) => new Set([...prev, newestEmergencyAlert.id]));
              }}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#cbd5e1',
                fontSize: '16px',
                cursor: 'pointer',
                padding: '2px 6px',
              }}
              title="Dismiss popup notification (does not resolve alert)"
            >
              ✕
            </button>
          </div>

          <div style={{ fontWeight: 600, fontSize: '14px', color: '#f8fafc' }}>
            {newestEmergencyAlert.title}
          </div>

          <div style={{ fontSize: '12px', color: '#e2e8f0', lineHeight: '1.4' }}>
            {newestEmergencyAlert.message}
          </div>

          <div
            style={{
              fontSize: '11px',
              color: '#94a3b8',
              display: 'flex',
              justifyContent: 'space-between',
              marginTop: '4px',
            }}
          >
            <span>📍 {newestEmergencyAlert.area} ({newestEmergencyAlert.radius_km} km target radius)</span>
            <span>
              {new Date(newestEmergencyAlert.created_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </div>

          <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
            <button
              className="btn-primary"
              style={{ flex: 1, fontSize: '12px', padding: '6px 12px' }}
              onClick={() => {
                setActivePage('Emergency Alerts');
                setDismissedAlertIds((prev) => new Set([...prev, newestEmergencyAlert.id]));
              }}
            >
              View Alert Details
            </button>
            <button
              className="btn-secondary"
              style={{ fontSize: '12px', padding: '6px 12px' }}
              onClick={() => {
                setDismissedAlertIds((prev) => new Set([...prev, newestEmergencyAlert.id]));
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Global Report Incident Modal */}
      {showReportModal && (
        <div className="modal-backdrop">
          <div className="modal-box" style={{ maxWidth: '650px' }}>
            <div className="modal-header">
              <h3>Report Emergency Flood Incident</h3>
              <button className="icon-btn" onClick={() => setShowReportModal(false)}>✕</button>
            </div>
            <div style={{ padding: '16px' }}>
              <IncidentReportView
                onSuccess={() => {
                  setShowReportModal(false);
                  loadAllData();
                  setActivePage('Rescue Operations');
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
