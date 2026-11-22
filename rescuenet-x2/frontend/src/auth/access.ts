import type { Role } from '../api/types';

export type Page =
  | 'Home' | 'Overview' | 'Flood Digital Twin' | 'Flood Forecasting' | 'Emergency Alerts'
  | 'Rescue Operations' | 'My Missions' | 'Volunteer Coordination' | 'Facilities & Shelters'
  | 'Incident Reports' | 'Report Emergency' | 'My Reports' | 'Rescue Records' | 'AI Supervisor'
  | 'Data & Models' | 'Diagnostics' | 'Admin Console' | 'Audit Log' | 'Settings' | 'My Account';

export interface NavSection {
  title: string;
  pages: Page[];
}

const PUBLIC_NAV: NavSection[] = [
  { title: 'Flood watch', pages: ['Home', 'Flood Digital Twin', 'Flood Forecasting', 'Emergency Alerts', 'Facilities & Shelters'] },
  { title: 'Help', pages: ['Report Emergency'] },
];

const DEPT_NAV: NavSection[] = [
  { title: 'Command', pages: ['Overview', 'Rescue Operations', 'AI Supervisor', 'Emergency Alerts'] },
  { title: 'Intelligence', pages: ['Flood Digital Twin', 'Flood Forecasting', 'Data & Models'] },
  { title: 'Resources', pages: ['Volunteer Coordination', 'Facilities & Shelters', 'Rescue Records', 'Incident Reports'] },
];

/** Sidebar layout for each role. Signed-out visitors get the public layout. */
export function navFor(role: Role | null): NavSection[] {
  switch (role) {
    // Administrators manage identities and the system; they hold no dispatch, triage, approval or alert rights
    // and cannot read incident data (see backend/app/core/permissions.py). Developers get diagnostics only.
    case 'ADMIN':
      return [
        { title: 'Administration', pages: ['Admin Console', 'Audit Log', 'Diagnostics', 'Settings', 'My Account'] },
        { title: 'Information', pages: ['Data & Models', 'Flood Forecasting', 'Emergency Alerts', 'Facilities & Shelters'] },
      ];
    case 'DEVELOPER':
      return [
        { title: 'Development', pages: ['Diagnostics', 'Data & Models'] },
        { title: 'Account', pages: ['My Account'] },
      ];
    case 'COMMANDER':
      return [...DEPT_NAV, { title: 'Administration', pages: ['Audit Log', 'My Account'] }];
    case 'OPERATOR':
      return [...DEPT_NAV, { title: 'Account', pages: ['My Account'] }];
    case 'RESCUE_OFFICER':
      return [
        { title: 'My team', pages: ['My Missions'] },
        { title: 'Situation', pages: ['Flood Digital Twin', 'Flood Forecasting', 'Emergency Alerts', 'Facilities & Shelters'] },
        { title: 'Reporting', pages: ['Report Emergency', 'Rescue Records'] },
        { title: 'Account', pages: ['My Account'] },
      ];
    case 'VOLUNTEER':
    case 'CITIZEN':
      return [...PUBLIC_NAV, { title: 'Account', pages: ['My Reports', 'My Account'] }];
    default:
      return PUBLIC_NAV;
  }
}

export const homePage = (role: Role | null): Page =>
  role === 'RESCUE_OFFICER' ? 'My Missions'
    : role === 'ADMIN' ? 'Admin Console'
    : role === 'DEVELOPER' ? 'Diagnostics'
    : role === 'COMMANDER' || role === 'OPERATOR' ? 'Overview' : 'Home';

export const isStaff = (role: Role | null) => role === 'COMMANDER' || role === 'OPERATOR';
export const isDepartment = (role: Role | null) => isStaff(role) || role === 'RESCUE_OFFICER';
export const canApprove = (role: Role | null) => role === 'COMMANDER';

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
