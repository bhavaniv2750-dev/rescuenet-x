import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { api } from './api/client';
import type { Alert, DashboardData, Facility, Incident, RescueTeam, RiverGauge, Volunteer } from './api/types';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { can, homePageOf, navSections, pageForPath, pathForPage } from './auth/access';
import type { Page } from './auth/access';
import { ConsoleShell } from './components/Layout/ConsoleShell';
import { PublicShell } from './components/Layout/PublicShell';
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
import { MfaEnrollment } from './components/Auth/MfaEnrollment';
import { SessionNeedsSignIn } from './components/Auth/RestrictedStates';
import { ResetPassword } from './components/Auth/ResetPassword';
import { ReportReceipt, type ReportReceiptData } from './components/UI/ReportReceipt';
import { MyWorkView } from './components/Views/MyWorkView';
import { AccountView } from './components/Views/AccountView';
import { AdminConsoleView } from './components/Views/AdminConsoleView';
import { toast } from './lib/toast';
import { AcceptInvitation } from './components/Auth/AcceptInvitation';
import { AgenciesView } from './components/Views/AgenciesView';
import { NotFoundPage, UnauthorizedPage } from './components/Routing/RouteProblems';
import type { Workspace } from './api/types';
import { ContactVerificationRequired } from './components/Auth/ContactVerificationRequired';

const GUEST_KEY = 'rescuenet.guest';

function Shell() {
  const { user, restoring, logout, refreshUser } = useAuth();

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
  // An invitation link opens the app as /#invite=TOKEN (the fragment is never sent to a server). Read once, then removed.
  const [inviteToken, setInviteToken] = useState<string | null>(() => {
    try {
      const t = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('invite');
      if (t) window.history.replaceState(null, '', window.location.pathname + window.location.search);
      return t;
    } catch {
      return null;
    }
  });
  const [guest, setGuest] = useState<boolean>(() => {
    try {
      // A public-namespace address (/public/...) is public information: it opens without an account.
      if (sessionStorage.getItem(GUEST_KEY) === '1') return true;
      if (window.location.pathname.startsWith('/public/')) { sessionStorage.setItem(GUEST_KEY, '1'); return true; }
      return false;
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

  const [activePage, setActivePageState] = useState<Page>('Home');
  const [routeProblem, setRouteProblem] = useState<'unauthorized' | 'notfound' | null>(null);
  const [guestWorkspace, setGuestWorkspace] = useState<Workspace | null>(null);
  // The server decides the workspace. A signed-in user's arrives with the user (no flash of the wrong navigation); a guest's is
  // fetched. Until it is known nothing is offered.
  const workspace: Workspace | null = user ? user.workspace ?? null : guest ? guestWorkspace : null;
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

  const dept = can(workspace, 'view_incidents');
  const staff = can(workspace, 'operations_console');
  const canApproveDispatch = can(workspace, 'approve_dispatch');
  const sections = useMemo(() => navSections(workspace), [workspace]);
  const wsKey = workspace ? `${workspace.experience}|${workspace.navigation.ids.join(',')}` : '';

  // Guests: ask the server for the public workspace.
  useEffect(() => {
    if (user || !guest) { if (user) setGuestWorkspace(null); return; }
    let live = true;
    api.getWorkspace().then((w) => live && setGuestWorkspace(w)).catch(() => undefined);
    return () => { live = false; };
  }, [user, guest]);

  /** Open a page: only pages the server offered exist. The address bar follows. */
  const navigate = useCallback((page: Page) => {
    const path = pathForPage(workspace, page);
    if (!path) return;                                  // not offered by the server: it cannot be opened
    setActivePageState(page);
    setRouteProblem(null);
    if (window.location.pathname !== path) window.history.pushState(null, '', path);
  }, [workspace]);

  // Resolve the address (initial load, back/forward, workspace change) against what the server offers.
  const resolveLocation = useCallback(() => {
    if (!workspace) return;
    const path = window.location.pathname.replace(/\/+$/, '') || '/';
    const page = pageForPath(workspace, path);
    if (page) { setActivePageState(page); setRouteProblem(null); return; }
    if (path === '/' || path === '/index.html') {
      const home = homePageOf(workspace);
      if (home) {
        setActivePageState(home); setRouteProblem(null);
        window.history.replaceState(null, '', pathForPage(workspace, home) || '/');
      }
      return;
    }
    setRouteProblem(workspace.known_paths.includes(path) ? 'unauthorized' : 'notfound');
  }, [workspace]);
  useEffect(() => { resolveLocation(); }, [wsKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    window.addEventListener('popstate', resolveLocation);
    return () => window.removeEventListener('popstate', resolveLocation);
  }, [resolveLocation]);

  // Signing in clears guest mode; signing out returns the address bar to the start page.
  const hadUser = useRef(false);
  useEffect(() => {
    if (user) setGuestMode(false);
    if (!user && hadUser.current) { window.history.replaceState(null, '', '/'); setRouteProblem(null); }
    hadUser.current = Boolean(user);
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the workspace fresh (activation steps, agency, capabilities): the server is the only source of truth.
  useEffect(() => {
    if (!user) return;
    const t = window.setInterval(() => { refreshUser(); }, 30000);
    return () => window.clearInterval(t);
  }, [user?.id, refreshUser]); // eslint-disable-line react-hooks/exhaustive-deps

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

  if (inviteToken && !user) {
    return <AcceptInvitation token={inviteToken} onDone={() => setInviteToken(null)} />;
  }

  if (restoring) {
    return (
      <div className="splash">
        <div className="spinner" aria-label="Loading" />
      </div>
    );
  }

  // Restricted authentication states are decided HERE, before any page of the app is rendered, so nobody briefly sees an
  // operational screen. The server enforces the same rules on every request; this only avoids showing pages that would fail.
  if (user?.password_change_required || user?.auth_state === 'PASSWORD_CHANGE_PENDING') {
    return <ForcedPasswordChange />;
  }
  if (user?.auth_state === 'CONTACT_VERIFICATION_PENDING') {
    return <ContactVerificationRequired />;
  }
  if (user?.auth_state === 'MFA_ENROLLMENT_PENDING') {
    return <MfaEnrollment mandatory userName={user.full_name} onDone={refreshUser} />;
  }
  if (user?.auth_state === 'MFA_CHALLENGE_PENDING') {
    return <SessionNeedsSignIn />;
  }

  if (!user && !guest) {
    return <LoginPage onContinueAsGuest={() => setGuestMode(true)}
      onReportEmergency={() => { window.history.replaceState(null, '', '/public/report'); setGuestMode(true); }} />;
  }

  // The server's answer is not here yet (a guest's public workspace is being fetched): offer nothing rather than the wrong thing.
  if (!workspace) {
    return (
      <div className="splash">
        <div className="spinner" aria-label="Loading" />
      </div>
    );
  }
  const goHome = () => { window.history.replaceState(null, '', '/'); setRouteProblem(null); resolveLocation(); };
  if (routeProblem === 'unauthorized') {
    return <UnauthorizedPage signedIn={Boolean(user)} onHome={goHome} onSignIn={() => setGuestMode(false)} />;
  }
  if (routeProblem === 'notfound') {
    return <NotFoundPage onHome={goHome} />;
  }

  const afterReport = (r?: ReportReceiptData) => {
    if (r) setReceipt(r);
    toast.success('Report sent. The control room has been notified.');
    loadAllData();
    navigate(staff ? 'Rescue Operations' : pathForPage(workspace, 'My Reports') ? 'My Reports' : 'Home');
  };

  const goReport = () => navigate(can(workspace, 'manage_incidents') ? 'Incident Reports' : 'Report Emergency');

  const intakeOnly = !can(workspace, 'manage_incidents');

  const content = (
    <>

          {receipt && <ReportReceipt receipt={receipt} onClose={() => setReceipt(null)} />}
          {activePage === 'Home' && (
            <PublicHomeView alerts={alerts} gauges={gauges} facilities={facilities} userName={user?.full_name} onNavigate={navigate} />
          )}

          {activePage === 'Overview' && (
            <OverviewView
              data={dashboardData}
              loading={refreshing && !dashboardData}
              onNavigate={(page) => navigate(page as Page)}
              onSelectIncident={() => navigate('Rescue Operations')}
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

          {activePage === 'Emergency Alerts' && <AlertsView alerts={alerts} onRefresh={loadAllData} canManage={staff} isCommander={canApproveDispatch} />}

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

          {activePage === 'AI Supervisor' && <SupervisorView incidents={incidents} canApprove={canApproveDispatch} />}

          {activePage === 'Data & Models' && <DatasetsView />}

          {activePage === 'Diagnostics' && <DiagnosticsView />}

          {activePage === 'Admin Console' && <AdminConsoleView canManageUsers teams={teams} />}
          {activePage === 'Agencies & Invitations' && <AgenciesView />}
          {activePage === 'Audit Log' && <AdminConsoleView canManageUsers={false} teams={teams} />}

          {activePage === 'Settings' && <SettingsView backendStatus={backendStatus} onRefresh={loadAllData} />}

          {activePage === 'My Account' && <AccountView />}
            </>
  );

  const canReport = Boolean(pathForPage(workspace, 'Report Emergency') || pathForPage(workspace, 'Incident Reports'));
  const guestBanner = guest && !user ? (
    <div className="guest-banner">
      You are browsing without an account.{' '}
      <button className="link-btn" onClick={() => setGuestMode(false)}>Sign in</button> to track your reports.
    </div>
  ) : null;

  // Two layout shells over the same pages, API client, session and permissions. The server's workspace picks the experience.
  if (workspace.experience === 'PUBLIC') {
    return (
      <PublicShell sections={sections} activePage={activePage} onNavigate={navigate} user={user} onSignIn={() => setGuestMode(false)} onSignOut={logout}
        onReport={() => navigate('Report Emergency')} badges={badges} banner={guestBanner}>
        {content}
      </PublicShell>
    );
  }
  return (
    <ConsoleShell sections={sections} activePage={activePage} onNavigate={navigate} user={user} backendStatus={backendStatus} refreshing={refreshing}
      onRefresh={loadAllData} onReport={canReport ? goReport : undefined} onSignOut={logout} badges={badges}>
      {content}
    </ConsoleShell>
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
