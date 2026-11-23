import { useState, useEffect, useCallback, useMemo } from 'react';
import './index.css';
import './theme.css';
import { api } from './api/client';
import type { Alert, DashboardData, Facility, Incident, RescueTeam, RiverGauge, Volunteer } from './api/types';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { canApprove, homePage, isDepartment, isStaff, navFor } from './auth/access';
import type { Page } from './auth/access';
import { Sidebar } from './components/Layout/Sidebar';
import { Topbar } from './components/Layout/Topbar';
import { LoginPage } from './components/Auth/LoginPage';
import { Toaster } from './components/UI/Toaster';
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
import { PublicHomeView } from './components/Views/PublicHomeView';
import { DiagnosticsView } from './components/Views/DiagnosticsView';
import { ForcedPasswordChange } from './components/Auth/ForcedPasswordChange';
import { ResetPassword } from './components/Auth/ResetPassword';
import { ReportReceipt, type ReportReceiptData } from './components/UI/ReportReceipt';
import { MyWorkView } from './components/Views/MyWorkView';
import { AccountView } from './components/Views/AccountView';
import { AdminConsoleView } from './components/Views/AdminConsoleView';
import { toast } from './lib/toast';

const GUEST_KEY = 'rescuenet.guest';

function Shell() {
  const { user, restoring, logout } = useAuth();
  const role = user?.role ?? null;

  // A signed-out visitor either sees the sign-in page or browses as a guest.
  const [receipt, setReceipt] = useState<ReportReceiptData | null>(null);
  // A password-reset link opens the app as /?reset=TOKEN. The token is read once and removed from the address bar so it does
  // not stay in the browser history or a Referer header.
  const [resetToken, setResetToken] = useState<string | null>(() => {
    try {
      const t = new URLSearchParams(window.location.search).get('reset');
      if (t) window.history.replaceState(null, '', window.location.pathname);
      return t;
    } catch {
      return null;
    }
  });
  const [guest, setGuest] = useState<boolean>(() => {
    try {
      return sessionStorage.getItem(GUEST_KEY) === '1';
    } catch {
      return false;
    }
  });
  const setGuestMode = (v: boolean) => {
    setGuest(v);
    try {
      v ? sessionStorage.setItem(GUEST_KEY, '1') : sessionStorage.removeItem(GUEST_KEY);
    } catch {
      /* ignore */
    }
  };

  const [activePage, setActivePage] = useState<Page>('Home');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [backendStatus, setBackendStatus] = useState('Checking...');
  const [refreshing, setRefreshing] = useState(false);

  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [teams, setTeams] = useState<RescueTeam[]>([]);
  const [volunteers, setVolunteers] = useState<Volunteer[]>([]);
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [gauges, setGauges] = useState<RiverGauge[]>([]);
  const [catchmentsGeoJSON, setCatchmentsGeoJSON] = useState<any>(null);

  const dept = isDepartment(role);
  const staff = isStaff(role);

  // Go to the right landing page when the signed-in user changes (sign-in, sign-out).
  useEffect(() => {
    setActivePage(homePage(role));
    if (user) setGuestMode(false);
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // If the user lands on a page their role does not have, send them home.
  const sections = useMemo(() => navFor(role), [role]);
  useEffect(() => {
    const allowed = new Set(sections.flatMap((s) => s.pages));
    if (!allowed.has(activePage)) setActivePage(homePage(role));
  }, [sections, activePage, role]);

  const loadAllData = useCallback(async () => {
    setRefreshing(true);
    try {
      await api.checkHealth();
      setBackendStatus('Connected');
    } catch {
      setBackendStatus('Offline');
      setRefreshing(false);
      return;
    }
    // Ask only for what this role is allowed to see.
    const jobs: Promise<unknown>[] = [
      api.getAlerts().then((r) => setAlerts(r.items)),
      api.getFacilities().then((r) => setFacilities(r.items)),
      api.getRiverGauges().then((r) => setGauges(r.items)),
      api.getCatchmentsGeoJSON().then(setCatchmentsGeoJSON),
    ];
    if (dept) {
      jobs.push(api.getIncidents().then((r) => setIncidents(r.items)), api.getTeams().then((r) => setTeams(r.items)));
    }
    if (staff) {
      jobs.push(api.getDashboard().then(setDashboardData), api.getVolunteers().then((r) => setVolunteers(r.items)));
    }
    await Promise.allSettled(jobs);
    setRefreshing(false);
  }, [dept, staff]);

  useEffect(() => {
    if (!user && !guest) return;
    loadAllData();
    const interval = setInterval(loadAllData, 15000);
    return () => clearInterval(interval);
  }, [loadAllData, user, guest]);

  const openIncidents = incidents.filter((i) => !['RESOLVED', 'DUPLICATE', 'CANCELLED'].includes(i.status)).length;
  const activeAlerts = alerts.filter((a) => a.status !== 'RESOLVED').length;
  const badges: Partial<Record<Page, number>> = {
    'Emergency Alerts': activeAlerts || undefined,
    'Rescue Operations': staff ? openIncidents || undefined : undefined,
  };

  if (resetToken) {
    return <ResetPassword token={resetToken} onDone={() => setResetToken(null)} />;
  }

  if (restoring) {
    return (
      <div className="splash">
        <div className="spinner" aria-label="Loading" />
      </div>
    );
  }

  if (user?.password_change_required) {
    return <ForcedPasswordChange />;
  }

  if (!user && !guest) {
    return <LoginPage onContinueAsGuest={() => { setGuestMode(true); setActivePage('Home'); }} />;
  }

  const afterReport = (r?: ReportReceiptData) => {
    if (r) setReceipt(r);
    toast.success('Report sent. The control room has been notified.');
    loadAllData();
    setActivePage(staff ? 'Rescue Operations' : user ? 'My Reports' : 'Home');
  };

  const goReport = () => setActivePage(dept && role !== 'RESCUE_OFFICER' ? 'Incident Reports' : 'Report Emergency');

  const intakeOnly = role !== 'ADMIN' && role !== 'COMMANDER' && role !== 'OPERATOR';

  return (
    <div className="app-shell">
      <Sidebar
        sections={sections}
        activePage={activePage}
        onNavigate={setActivePage}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        backendStatus={backendStatus}
        badges={badges}
      />

      <div className="app-main">
        <Topbar
          activePage={activePage}
          user={user}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          onRefresh={loadAllData}
          onReport={goReport}
          onOpenAccount={() => setActivePage('My Account')}
          onSignIn={() => setGuestMode(false)}
          onSignOut={logout}
          refreshing={refreshing}
          backendStatus={backendStatus}
        />

        {guest && !user && (
          <div className="guest-banner">
            You are browsing without an account.{' '}
            <button className="link-btn" onClick={() => setGuestMode(false)}>
              Sign in
            </button>{' '}
            to track your reports.
          </div>
        )}

        <main className="page-viewport" key={activePage}>
          {receipt && <ReportReceipt receipt={receipt} onClose={() => setReceipt(null)} />}
          {activePage === 'Home' && (
            <PublicHomeView alerts={alerts} gauges={gauges} facilities={facilities} userName={user?.full_name} onNavigate={setActivePage} />
          )}

          {activePage === 'Overview' && (
            <OverviewView
              data={dashboardData}
              loading={refreshing && !dashboardData}
              onNavigate={(page) => setActivePage(page as Page)}
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
              incidents={dept ? incidents : []}
              teams={dept ? teams : []}
              facilities={facilities}
              gauges={gauges}
              alerts={alerts}
            />
          )}

          {activePage === 'Flood Forecasting' && <ForecastingView initialForecast={dashboardData?.forecast_preview} />}

          {activePage === 'Emergency Alerts' && <AlertsView alerts={alerts} onRefresh={loadAllData} canManage={staff} isCommander={canApprove(role)} />}

          {activePage === 'Rescue Operations' && (
            <RescueOperationsView incidents={incidents} teams={teams} onRefresh={loadAllData} onOpenReportModal={goReport} />
          )}

          {activePage === 'My Missions' && <MyWorkView variant="missions" teamName={user?.team_id} />}
          {activePage === 'My Reports' && <MyWorkView variant="reports" />}

          {activePage === 'Volunteer Coordination' && <VolunteersView volunteers={volunteers} incidents={incidents} onRefresh={loadAllData} />}

          {activePage === 'Facilities & Shelters' && <FacilitiesView facilities={facilities} onRefresh={loadAllData} canManage={staff} />}

          {(activePage === 'Incident Reports' || activePage === 'Report Emergency') && (
            <IncidentReportView intakeOnly={intakeOnly || activePage === 'Report Emergency'} onSuccess={afterReport} />
          )}

          {activePage === 'Rescue Records' && <RescueRecordsView />}

          {activePage === 'AI Supervisor' && <SupervisorView incidents={incidents} canApprove={canApprove(role)} />}

          {activePage === 'Data & Models' && <DatasetsView />}

          {activePage === 'Diagnostics' && <DiagnosticsView />}

          {activePage === 'Admin Console' && <AdminConsoleView canManageUsers teams={teams} />}
          {activePage === 'Audit Log' && <AdminConsoleView canManageUsers={false} teams={teams} />}

          {activePage === 'Settings' && <SettingsView backendStatus={backendStatus} onRefresh={loadAllData} />}

          {activePage === 'My Account' && <AccountView />}
        </main>
      </div>

    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <Shell />
      <Toaster />
    </AuthProvider>
  );
}

export default App;
