import type {
  Alert,
  DashboardData,
  DatasetItem,
  Facility,
  FloodPredictionResult,
  Incident,
  RescueRecord,
  RescueTeam,
  RiverGauge,
  SupervisorTask,
  Volunteer,
} from './types';

// Default to backend port 8000
const API_BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

/** Turn a server path such as /api/datasets/images/file/x.jpg into a full URL on the API host. */
export function assetUrl(path?: string | null): string {
  if (!path) return '';
  if (/^(https?:|data:|blob:)/.test(path)) return path;
  return `${API_BASE_URL.replace(/\/api\/?$/, '')}${path}`;
}

// ---- session ----
// The short-lived access token lives ONLY in memory (never localStorage or sessionStorage). The long-lived refresh token is
// an HttpOnly cookie the page cannot read. A page reload therefore restores the session by calling /auth/refresh.
const LEGACY_TOKEN_KEY = 'rescuenet.token';
let accessToken: string | null = null;
let csrfToken: string | null = null;

// Remove any token the previous (pre-S2) version left in browser storage.
try {
  sessionStorage.removeItem(LEGACY_TOKEN_KEY);
  localStorage.removeItem(LEGACY_TOKEN_KEY);
} catch {
  /* storage blocked: nothing to clean */
}

function readCookie(name: string): string | null {
  const m = document.cookie.split('; ').find((c) => c.startsWith(name + '='));
  return m ? decodeURIComponent(m.slice(name.length + 1)) : null;
}

export const tokenStore = {
  get(): string | null {
    return accessToken;
  },
  set(token: string, csrf?: string) {
    accessToken = token;
    if (csrf) csrfToken = csrf;
  },
  clear() {
    accessToken = null;
    csrfToken = null;
  },
};

export const UNAUTHORIZED_EVENT = 'rescuenet:unauthorized';

type SessionResponse = import('./types').TokenResponse;
let refreshing: Promise<SessionResponse | null> | null = null;

/** Exchange the refresh cookie for a new access token. One request at a time in this tab, and one at a time across tabs
 *  (Web Locks), because a refresh token can be used only once: two simultaneous uses would look like theft. */
export function refreshSession(): Promise<SessionResponse | null> {
  if (refreshing) return refreshing;
  const run = async (): Promise<SessionResponse | null> => {
    try {
      const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRF-Token': readCookie('rn_csrf') || csrfToken || '' },
      });
      if (!res.ok) {
        if (res.status === 401) tokenStore.clear();
        return null;
      }
      const body = (await res.json()) as SessionResponse;
      tokenStore.set(body.access_token, body.csrf_token);
      return body;
    } catch {
      return null; // network problem: keep what we have and try again later
    }
  };
  const locks = (navigator as Navigator & { locks?: { request: <T>(n: string, cb: () => Promise<T>) => Promise<T> } }).locks;
  refreshing = (locks ? locks.request('rescuenet-refresh', run) : run()).finally(() => {
    refreshing = null;
  });
  return refreshing;
}

// Endpoints that set or use the session cookies. Accepting an invitation starts a session, so it must send/receive them too
// (found in the S6 browser run: without this the new session's cookies were dropped and a reload signed the new owner out).
const usesCookies = (endpoint: string) => endpoint.startsWith('/auth/') || endpoint === '/invitations/accept';

async function request<T>(endpoint: string, options: RequestInit = {}, retried = false): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const token = tokenStore.get();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(url, { ...options, headers, credentials: usesCookies(endpoint) ? 'include' : 'same-origin' });
  if (response.status === 401 && token && !retried && !endpoint.startsWith('/auth/login') && !endpoint.startsWith('/auth/refresh')) {
    // The access token expired (or was revoked). Try once to get a new one; if that fails the session is over.
    const renewed = await refreshSession();
    if (renewed) return request<T>(endpoint, options, true);
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
  }
  if (!response.ok) {
    const errorBody = await response.text();
    let detail = response.statusText;
    try {
      const parsed = JSON.parse(errorBody);
      detail = parsed.detail || detail;
    } catch {
      detail = errorBody || detail;
    }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : JSON.stringify(detail), response.headers.get('x-mfa-reauth-required') === 'true');
  }

  return response.json();
}

export class ApiError extends Error {
  status: number;
  /** True when the server wants a fresh authenticator code before this sensitive action (X-MFA-Reauth-Required). */
  reauth: boolean;
  constructor(status: number, message: string, reauth = false) {
    super(message);
    this.status = status;
    this.reauth = reauth;
  }
}

/** Link to the CAP 1.2 XML for an alert (opens in a new tab, no sign-in needed). */
export const capUrl = (alertId: string) => `${API_BASE_URL}/alerts/${encodeURIComponent(alertId)}/cap`;

export const api = {
  // ---- authentication ----
  getPortals: () => request<import('./types').PortalInfo>('/auth/portals'),
  login: (username: string, password: string, remember = false) =>
    request<import('./types').TokenResponse | import('./types').MfaChallengeResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ portal: 'auto', username, password, remember }) }),
  /** Second step of sign-in: an authenticator code or a recovery code, with the single-use challenge from the password step. */
  mfaVerify: (challenge_token: string, input: { code?: string; recovery_code?: string }) =>
    request<import('./types').TokenResponse>('/auth/mfa/verify', { method: 'POST', body: JSON.stringify({ challenge_token, ...input }) }),
  mfaStatus: () => request<import('./types').MfaStatus>('/auth/mfa/status'),
  mfaEnrollStart: (current_password: string) =>
    request<import('./types').MfaEnrollStart>('/auth/mfa/enroll/start', { method: 'POST', body: JSON.stringify({ current_password }) }),
  mfaEnrollConfirm: (code: string) =>
    request<{ enabled: boolean; recovery_codes: string[]; instructions: string }>('/auth/mfa/enroll/confirm', { method: 'POST', body: JSON.stringify({ code }) }),
  mfaReauth: (code: string) => request<{ fresh_for_minutes: number }>('/auth/mfa/reauth', { method: 'POST', body: JSON.stringify({ code }) }),
  mfaDisable: (current_password: string) => request<{ enabled: boolean }>('/auth/mfa/disable', { method: 'POST', body: JSON.stringify({ current_password }) }),
  regenerateRecoveryCodes: () => request<{ recovery_codes: string[]; instructions: string }>('/auth/mfa/recovery-codes/regenerate', { method: 'POST' }),
  logout: () => request<{ message: string }>('/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': readCookie('rn_csrf') || csrfToken || '' } }),
  logoutAll: () => request<{ message: string; sessions_ended: number }>('/auth/logout-all', { method: 'POST' }),
  getSessions: () => request<{ items: import('./types').SessionInfo[]; count: number }>('/auth/sessions'),
  revokeSession: (id: string) => request<{ message: string; was_current: boolean }>(`/auth/sessions/${id}`, { method: 'DELETE' }),
  revokeUserSessions: (userId: number) => request<{ message: string }>(`/auth/users/${userId}/revoke-sessions`, { method: 'POST' }),
  register: (payload: import('./types').RegisterPayload) =>
    request<import('./types').TokenResponse>('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  getMe: () => request<import('./types').AuthUser>('/auth/me'),
  /** The caller's workspace. Open to guests (public workspace). */
  getWorkspace: () => request<import('./types').Workspace>('/auth/workspace'),
  // ---- agencies and invitations (S5/S6)
  getAgencies: () => request<{ items: import('./types').AgencyRow[]; count: number; types: string[] }>('/agencies'),
  getAgency: (id: number) => request<import('./types').AgencyRow>(`/agencies/${id}`),
  createAgency: (payload: { name: string; agency_type: string; region?: string }) =>
    request<import('./types').AgencyRow>('/agencies', { method: 'POST', body: JSON.stringify(payload) }),
  updateAgency: (id: number, payload: Record<string, unknown>) =>
    request<import('./types').AgencyRow>(`/agencies/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  setMemberAgency: (userId: number, agency_id: number | null) =>
    request<{ user_id: number; agency_id: number | null }>(`/agencies/members/${userId}`, { method: 'PUT', body: JSON.stringify({ agency_id }) }),
  setTeamAgency: (teamId: string, agency_id: number | null) =>
    request<{ team_id: string; agency_id: number | null }>(`/agencies/teams/${teamId}`, { method: 'PUT', body: JSON.stringify({ agency_id }) }),
  getInvitations: () => request<{ items: import('./types').InvitationRow[]; count: number; note: string }>('/invitations'),
  revokeInvitation: (id: number) => request<{ revoked: boolean; status: string }>(`/invitations/${id}/revoke`, { method: 'POST' }),
  /** Invitations (S5). The token travels in the request body, never in a URL. Unusable invitations all answer the same 404. */
  inspectInvitation: (token: string) =>
    request<import('./types').InvitationPreview>('/invitations/inspect', { method: 'POST', body: JSON.stringify({ token }) }),
  acceptInvitation: (payload: { token: string; username: string; full_name: string; password: string; phone?: string }) =>
    request<import('./types').TokenResponse>('/invitations/accept', { method: 'POST', body: JSON.stringify(payload) }),
  getCapabilities: () => request<import('./types').Capabilities>('/auth/capabilities'),
  /** Always answers the same way; it never says whether an account exists. */
  forgotPassword: (identifier: string) =>
    request<{ message: string; delivery_mode: string }>('/auth/password/forgot', { method: 'POST', body: JSON.stringify({ identifier }) }),
  resetPassword: (token: string, new_password: string) =>
    request<{ message: string }>('/auth/password/reset', { method: 'POST', body: JSON.stringify({ token, new_password }) }),
  requestVerification: (channel: 'email' | 'phone') =>
    request<{ already_verified: boolean; message: string; delivery_status?: string; cooldown_seconds?: number }>(`/auth/verify/${channel}/request`, { method: 'POST' }),
  confirmVerification: (channel: 'email' | 'phone', code: string) =>
    request<{ verified: boolean }>(`/auth/verify/${channel}/confirm`, { method: 'POST', body: JSON.stringify({ code }) }),
  changeContact: (payload: { current_password: string; email?: string; phone?: string }) =>
    request<{ changed: string[]; message: string; user: import('./types').AuthUser }>('/auth/me/contact', { method: 'PATCH', body: JSON.stringify(payload) }),
  /** Development only: 404 everywhere else. Nothing in it was delivered to anyone. */
  getDevOutbox: () => request<{ notice: string; items: import('./types').DevOutboxMessage[] }>('/dev/outbox'),
  /** Every session ends when the password changes; the server starts a fresh one for this device and returns its tokens. */
  changePassword: async (current_password: string, new_password: string) => {
    const res = await request<{ message: string; sessions_ended: number } & import('./types').TokenResponse>('/auth/me/password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    });
    tokenStore.set(res.access_token, res.csrf_token);
    return res;
  },
  getUsers: () => request<{ items: import('./types').AuthUser[]; count: number; roles: string[] }>('/auth/users'),
  createUser: (payload: Record<string, unknown>) =>
    request<import('./types').AuthUser>('/auth/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (id: number, payload: Record<string, unknown>) =>
    request<import('./types').AuthUser>(`/auth/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  getAuditLog: (limit = 100, action?: string) =>
    request<{ items: import('./types').AuditEntry[]; count: number }>(`/auth/audit?limit=${limit}${action ? `&action=${action}` : ''}`),
  getTeamOptions: () => request<{ items: { id: string; name: string }[] }>('/auth/team-options'),
  getDiagnostics: () => request<Record<string, any>>('/diagnostics/'),
  getMyIncidents: () => request<{ items: Incident[]; count: number }>('/incidents/mine'),

  // Health
  checkHealth: () => request<any>('/health'),

  // Dashboard
  getDashboard: () => request<DashboardData>('/dashboard'),

  // Incidents
  getIncidents: (params?: { status?: string; severity?: string; search?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.severity) query.set('severity', params.severity);
    if (params?.search) query.set('search', params.search);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request<{ items: Incident[]; count: number }>(`/incidents/${qs}`);
  },

  uploadIncidentImage: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const url = `${API_BASE_URL}/incidents/upload-image`;
    const token = tokenStore.get();
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!response.ok) {
      const err = await response.text();
      let detail = response.statusText;
      try {
        const parsed = JSON.parse(err);
        detail = parsed.detail || detail;
      } catch {
        detail = err || detail;
      }
      throw new Error(`Upload failed: ${detail}`);
    }
    return response.json() as Promise<{
      status: string;
      image_url: string;
      filename: string;
      size_bytes: number;
    }>;
  },

  /** Private evidence photo, fetched with the sign-in token (a plain <img> cannot send it). */
  getEvidenceBlob: async (path: string): Promise<Blob> => {
    const token = tokenStore.get();
    const response = await fetch(assetUrl(path), { headers: token ? { Authorization: `Bearer ${token}` } : undefined });
    if (!response.ok) throw new ApiError(response.status, 'Photo not available');
    return response.blob();
  },

  /** Follow a report without an account. The tracking code goes in a header, never in the URL. */
  trackReport: async (ref: string, code: string) => {
    const response = await fetch(`${API_BASE_URL}/public/reports/${encodeURIComponent(ref.trim())}`, {
      headers: { 'X-Tracking-Code': code.trim() },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new ApiError(response.status, typeof body.detail === 'string' ? body.detail : 'Could not look up that report.');
    return body as { public_ref: string; status: string; received_at: string; updated_at: string; photo_count: number; notice: string };
  },

  createIncident: (payload: {
    title: string;
    description: string;
    area: string;
    latitude: number;
    longitude: number;
    severity: string;
    people_affected: number;
    source?: string;
    incident_type?: string;
    image_url?: string | null;
    reporter_name?: string | null;
    reporter_contact?: string | null;
    reported_water_depth?: string | null;
  }) => request<Incident & { tracking_code?: string; photos_attached?: number; photo_warnings?: string[] }>('/incidents/', { method: 'POST', body: JSON.stringify(payload) }),

  updateIncident: (id: string, payload: { status?: string; assigned_team_id?: string; severity?: string; image_url?: string | null }) =>
    request<Incident>(`/incidents/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  changeIncidentState: (id: string, toStatus: string, extra: { actor?: string; note?: string; duplicate_of?: string } = {}) =>
    request<Incident>(`/incidents/${id}/state`, { method: 'POST', body: JSON.stringify({ to_status: toStatus, ...extra }) }),

  getIncidentHistory: (id: string) =>
    request<{ items: import('./types').AuditEntry[]; count: number }>(`/incidents/${id}/history`),

  getIncidentLifecycle: () =>
    request<{ states: string[]; transitions: Record<string, string[]>; terminal_states: string[] }>('/incidents/lifecycle'),

  getBeacons: () => request<{ items: import('./types').Beacon[]; count: number }>('/incidents/beacons'),

  analyzeIncidentPhoto: (id: string) =>
    request<Incident>(`/incidents/${id}/analyze-photo`, { method: 'POST' }),

  analyzeDatasetImage: (filename: string) =>
    request<import('./types').VisionAnalysis>(`/vision/dataset/${encodeURIComponent(filename)}`),

  getVisionStatus: () => request<{ ready: boolean; loaded: boolean; weights_present: boolean; runtime_installed: boolean; last_error?: string | null }>('/vision/status'),

  deleteIncident: (id: string) => request<{ message: string }>(`/incidents/${id}`, { method: 'DELETE' }),

  getRecordsCSVUrl: () => `${API_BASE_URL}/records/export/csv`,

  apiBaseUrl: API_BASE_URL,

  // Alerts
  getAlerts: (statusFilter?: string) => {
    const qs = statusFilter ? `?status_filter=${statusFilter}` : '';
    return request<{ items: Alert[]; count: number; active_count: number }>(`/alerts/${qs}`);
  },

  createAlert: (payload: {
    title: string;
    message: string;
    severity: string;
    area: string;
    latitude: number;
    longitude: number;
    radius_km: number;
  }) => request<Alert>('/alerts/', { method: 'POST', body: JSON.stringify(payload) }),

  acknowledgeAlert: (alertId: string) =>
    request<Alert>(`/alerts/${alertId}/acknowledge`, { method: 'POST' }),

  resolveAlert: (alertId: string) =>
    request<Alert>(`/alerts/${alertId}/resolve`, { method: 'POST' }),

  // Teams
  getTeams: (statusFilter?: string) => {
    const qs = statusFilter ? `?status=${statusFilter}` : '';
    return request<{ items: RescueTeam[]; count: number; available_count: number }>(`/teams/${qs}`);
  },

  assignTeam: (teamId: string, incidentId: string) =>
    request<any>(`/teams/${teamId}/assign`, { method: 'POST', body: JSON.stringify({ incident_id: incidentId }) }),

  updateTeamStatus: (teamId: string, status: string) =>
    request<RescueTeam>(`/teams/${teamId}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),

  // Volunteers
  getVolunteers: (params?: { verified?: boolean; skill?: string }) => {
    const query = new URLSearchParams();
    if (params?.verified !== undefined) query.set('verified', String(params.verified));
    if (params?.skill) query.set('skill', params.skill);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request<{ items: Volunteer[]; count: number; verified_count: number }>(`/volunteers/${qs}`);
  },

  registerVolunteer: (payload: { name: string; phone: string; email: string; skills: string; area: string }) =>
    request<Volunteer>('/volunteers/', { method: 'POST', body: JSON.stringify(payload) }),

  assignVolunteer: (volunteerId: string, incidentId: string) =>
    request<Volunteer>(`/volunteers/${volunteerId}/assign`, { method: 'POST', body: JSON.stringify({ incident_id: incidentId }) }),

  releaseVolunteer: (volunteerId: string) => request<Volunteer>(`/volunteers/${volunteerId}/release`, { method: 'POST' }),

  updateFacilityOccupancy: (facilityId: string, current_occupancy: number) =>
    request<Facility>(`/facilities/${facilityId}/occupancy`, { method: 'PATCH', body: JSON.stringify({ current_occupancy }) }),

  updateVolunteer: (volunteerId: string, payload: { is_verified?: boolean; status?: string }) =>
    request<Volunteer>(`/volunteers/${volunteerId}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  // Facilities
  getFacilities: (params?: { type?: string; lat?: number; lon?: number }) => {
    const query = new URLSearchParams();
    if (params?.type) query.set('type', params.type);
    if (params?.lat !== undefined) query.set('lat', String(params.lat));
    if (params?.lon !== undefined) query.set('lon', String(params.lon));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request<{ items: Facility[]; count: number; total_capacity: number; total_occupancy: number }>(`/facilities/${qs}`);
  },

  createFacility: (payload: any) =>
    request<Facility>('/facilities/', { method: 'POST', body: JSON.stringify(payload) }),

  // Records
  getRecords: () => request<{ items: RescueRecord[]; count: number }>('/records/'),

  getRecordsSummary: () => request<any>('/records/summary'),

  createRecord: (payload: any) =>
    request<RescueRecord>('/records/', { method: 'POST', body: JSON.stringify(payload) }),

  // Flood & GIS
  getFloodStatus: () => request<any>('/flood/status'),

  predictFlood: (scenario: { rainfall_mm: number; water_level_m: number; humidity_pct?: number; temperature_c?: number }) =>
    request<FloodPredictionResult>('/flood/forecast', { method: 'POST', body: JSON.stringify(scenario) }),

  getCatchmentsGeoJSON: () => request<any>('/flood/catchments'),

  getRiverGauges: () => request<{ count: number; items: RiverGauge[] }>('/flood/gauges'),

  // Agents & Supervisor
  getAgents: () => request<any>('/agents/'),

  getSupervisorTasks: () => request<{ items: SupervisorTask[]; count: number }>('/agents/tasks'),

  executeSupervisorTriage: (payload: { task_type: string; incident_id?: string; area?: string; instruction?: string }) =>
    request<SupervisorTask>('/agents/supervisor/triage', { method: 'POST', body: JSON.stringify(payload) }),

  approveSupervisorTask: (taskId: string, note?: string) =>
    request<SupervisorTask>(`/agents/tasks/${taskId}/approve`, { method: 'POST', body: JSON.stringify({ note }) }),

  declineSupervisorTask: (taskId: string, note?: string) =>
    request<SupervisorTask>(`/agents/tasks/${taskId}/decline`, { method: 'POST', body: JSON.stringify({ note }) }),

  // Datasets & Models
  getDatasets: () => request<{ count: number; items: DatasetItem[]; storage_root: string; total_records_ingested: number; flood_images_verified: number; flood_images_unique?: number; duplicate_images_count?: number }>('/datasets/inventory'),

  getModels: () => request<{ count: number; models: import('./types').ModelItem[]; active_forecaster: string; vision_model_configured: boolean }>('/datasets/models'),

  getFloodImages: (params?: { page?: number; page_size?: number; search?: string; format?: string; collection?: string }) => {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.page_size) query.set('page_size', String(params.page_size));
    if (params?.search) query.set('search', params.search);
    if (params?.format) query.set('format', params.format);
    if (params?.collection) query.set('collection', params.collection);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return request<import('./types').PaginatedImagesResponse>(`/datasets/images${qs}`);
  },

  inspectImage: (filename: string) =>
    request<import('./types').ImageInspectionResult>(`/datasets/images/inspect/${encodeURIComponent(filename)}`),

  preprocessImage: (filename: string) =>
    request<import('./types').ImagePreprocessingResult>(`/datasets/images/preprocess/${encodeURIComponent(filename)}`, { method: 'POST' }),

  getImageFileUrl: (filename: string) =>
    `${API_BASE_URL}/datasets/images/file/${encodeURIComponent(filename)}`,
};
