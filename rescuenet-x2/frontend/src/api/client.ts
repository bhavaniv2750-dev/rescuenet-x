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

// ---- session token (sessionStorage by default, localStorage when "remember me" is ticked) ----
const TOKEN_KEY = 'rescuenet.token';

export const tokenStore = {
  get(): string | null {
    try {
      return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string, remember: boolean) {
    try {
      this.clear();
      (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token);
    } catch {
      /* storage blocked: the session lasts until the page reloads */
    }
  },
  clear() {
    try {
      sessionStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};

export const UNAUTHORIZED_EVENT = 'rescuenet:unauthorized';

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const token = tokenStore.get();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(url, { ...options, headers });
  if (response.status === 401 && token && !endpoint.startsWith('/auth/login')) {
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
    throw new ApiError(response.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }

  return response.json();
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Link to the CAP 1.2 XML for an alert (opens in a new tab, no sign-in needed). */
export const capUrl = (alertId: string) => `${API_BASE_URL}/alerts/${encodeURIComponent(alertId)}/cap`;

export const api = {
  // ---- authentication ----
  getPortals: () => request<import('./types').PortalInfo>('/auth/portals'),
  login: (portal: string, username: string, password: string) =>
    request<import('./types').TokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ portal, username, password }) }),
  register: (payload: import('./types').RegisterPayload) =>
    request<import('./types').TokenResponse>('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  getMe: () => request<import('./types').AuthUser>('/auth/me'),
  changePassword: (current_password: string, new_password: string) =>
    request<{ message: string }>('/auth/me/password', { method: 'POST', body: JSON.stringify({ current_password, new_password }) }),
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
