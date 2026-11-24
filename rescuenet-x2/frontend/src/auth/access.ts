import type { Role, Workspace } from '../api/types';

/** Page names used by the views. The backend decides WHICH of them exist for a caller (see backend/app/core/navigation.py):
 *  this file holds no role rules. A name the server never offers cannot be opened. */
export type Page =
  | 'Home' | 'Overview' | 'Flood Digital Twin' | 'Flood Forecasting' | 'Emergency Alerts'
  | 'Rescue Operations' | 'My Missions' | 'Volunteer Coordination' | 'Facilities & Shelters'
  | 'Incident Reports' | 'Report Emergency' | 'My Reports' | 'Rescue Records' | 'AI Supervisor'
  | 'Data & Models' | 'Diagnostics' | 'Admin Console' | 'Agencies & Invitations' | 'Audit Log' | 'Settings' | 'My Account';

export interface NavSection {
  title: string;
  pages: Page[];
}

/** Sidebar sections exactly as the server listed them (empty while the workspace is unknown or activation is incomplete). */
export function navSections(ws: Workspace | null): NavSection[] {
  return (ws?.navigation.sections ?? []).map((s) => ({ title: s.title, pages: s.items.map((i) => i.label as Page) }));
}

/** page label -> path, and path -> page label, for the entries the server offered. */
export function pathForPage(ws: Workspace | null, page: Page): string | null {
  for (const s of ws?.navigation.sections ?? []) for (const i of s.items) if (i.label === page) return i.path;
  return null;
}
export function pageForPath(ws: Workspace | null, path: string): Page | null {
  for (const s of ws?.navigation.sections ?? []) for (const i of s.items) if (i.path === path) return i.label as Page;
  return null;
}
export function homePageOf(ws: Workspace | null): Page | null {
  const home = ws?.navigation.home ?? null;
  return home ? pageForPath(ws, home) : null;
}

export const can = (ws: Workspace | null, capability: string): boolean => Boolean(ws?.capabilities?.[capability]);

export const ROLE_LABEL: Record<Role, string> = {
  ADMIN: 'Administrator',
  DEVELOPER: 'Developer (diagnostics)',
  COMMANDER: 'Incident Commander',
  OPERATOR: 'Control Room Operator',
  RESCUE_OFFICER: 'Rescue Officer',
  VOLUNTEER: 'Volunteer',
  CITIZEN: 'Citizen',
};

export const PORTAL_HOME: Record<string, string> = {
  public: 'Citizens & Volunteers',
  operations: 'Rescue Operations Department',
  admin: 'Admin & Developers',
};
