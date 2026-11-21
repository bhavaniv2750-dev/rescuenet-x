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

  // Initial load and periodic polling
  useEffect(() => {
    loadAllData();
    const interval = setInterval(loadAllData, 15000);
    return () => clearInterval(interval);
  }, [loadAllData]);

  const activeAlertsCount = alerts.filter((a) => a.status === 'ACTIVE').length;
  const activeIncidentsCount = incidents.filter((i) => !['RESOLVED', 'DUPLICATE', 'CANCELLED'].includes(i.status)).length;

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
          backendStatus={backendStatus}
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
