import { describe, expect, it } from 'vitest';
import type { Workspace } from '../api/types';
import { can, homePageOf, navSections, pageForPath, pathForPage } from './access';

const ws = (over: Partial<Workspace> = {}): Workspace => ({
  experience: 'PROFESSIONAL', authenticated: true,
  activation: { state: 'AUTHENTICATED', complete: true, restricted_reason: null, remaining_steps: [] },
  assurance: { level: 'MFA', mfa_enabled: true, mfa_required: true, recent_mfa: true }, agency_id: null, team_id: null,
  capabilities: { approve_dispatch: true, manage_alerts: false },
  navigation: { sections: [{ id: 'command', title: 'Command', items: [{ id: 'overview', label: 'Overview', path: '/console/overview' }, { id: 'ops', label: 'Rescue Operations', path: '/console/operations' }] }], ids: ['overview', 'ops'], home: '/console/overview', home_id: 'overview' },
  known_paths: ['/console/overview', '/console/operations', '/console/admin'], ...over,
});

describe('navigation helpers (the server decides; the client only renders)', () => {
  it('lists exactly the sections the server offered', () => { expect(navSections(ws())).toEqual([{ title: 'Command', pages: ['Overview', 'Rescue Operations'] }]); });
  it('offers nothing while the workspace is unknown', () => { expect(navSections(null)).toEqual([]); expect(homePageOf(null)).toBeNull(); });
  it('maps pages to paths and back, and refuses pages that were not offered', () => {
    expect(pathForPage(ws(), 'Rescue Operations')).toBe('/console/operations');
    expect(pageForPath(ws(), '/console/operations')).toBe('Rescue Operations');
    expect(pathForPage(ws(), 'Admin Console')).toBeNull(); expect(pageForPath(ws(), '/console/admin')).toBeNull();
  });
  it('finds the landing page', () => { expect(homePageOf(ws())).toBe('Overview'); });
  it('capabilities are plain booleans from the server', () => { expect(can(ws(), 'approve_dispatch')).toBe(true); expect(can(ws(), 'manage_alerts')).toBe(false); expect(can(ws(), 'unknown')).toBe(false); expect(can(null, 'approve_dispatch')).toBe(false); });
});
