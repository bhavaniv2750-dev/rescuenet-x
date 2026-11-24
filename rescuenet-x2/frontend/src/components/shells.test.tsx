import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthLayout } from './Auth/AuthLayout';
import { ConsoleShell } from './Layout/ConsoleShell';
import { PublicShell } from './Layout/PublicShell';
import { NotFoundPage, UnauthorizedPage } from './Routing/RouteProblems';
import { ReportReceipt } from './UI/ReportReceipt';
import { DataNotice } from './ui';
import type { NavSection } from '../auth/access';

vi.mock('../api/client', () => ({
  api: { getPortals: vi.fn().mockResolvedValue({ demo_mode: false, portals: [] }), login: vi.fn(), register: vi.fn(), logout: vi.fn(), getMe: vi.fn() },
  refreshSession: vi.fn().mockResolvedValue(null), tokenStore: { get: () => null, set: vi.fn(), clear: vi.fn() }, UNAUTHORIZED_EVENT: 'rn-unauthorized',
}));

const sections: NavSection[] = [{ title: 'Flood watch', pages: ['Home', 'Emergency Alerts', 'Report Emergency'] }];

beforeEach(() => { try { localStorage.clear(); } catch { /* ignore */ } });

describe('AuthLayout', () => {
  it('shows the product name and nothing academic, promotional or credential-like', () => {
    const { container } = render(<AuthLayout><p>form</p></AuthLayout>);
    expect(container.textContent).toMatch(/RescueNet/);
    expect(container.textContent).not.toMatch(/College|Engineering|Student|Department|Government|Rescue@|demo|password:/i);
  });
});

describe('LoginPage', () => {
  it('offers sign-in, registration for citizens and volunteers only, forgot password and guest reporting, and no demo shortcuts', async () => {
    const { AuthProvider } = await import('../auth/AuthContext');
    const { LoginPage } = await import('./Auth/LoginPage');
    const onReport = vi.fn();
    render(<AuthProvider><LoginPage onContinueAsGuest={() => {}} onReportEmergency={onReport} /></AuthProvider>);
    expect(await screen.findByLabelText('Email or username')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    await userEvent.click(screen.getByRole('button', { name: /show password/i }));
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'text');
    expect(screen.getByRole('button', { name: /forgot password/i })).toBeInTheDocument();
    expect(screen.queryByText(/demo account|Tap one|password:/i)).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: /report an emergency without signing in/i }));
    expect(onReport).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: /create a citizen or volunteer account/i }));
    const types = within(screen.getByRole('radiogroup', { name: 'Account type' })).getAllByRole('radio').map((r) => r.textContent);
    expect(types).toEqual(['Citizen', 'Volunteer']);          // no staff, administrator or developer registration
  });
});

describe('PublicShell', () => {
  it('has the portal navigation, an always-available emergency report action, a skip link and the emergency numbers', async () => {
    const onReport = vi.fn(); const onNavigate = vi.fn();
    render(<PublicShell sections={sections} activePage="Home" onNavigate={onNavigate} user={null} onSignIn={() => {}} onSignOut={() => {}} onReport={onReport}><p>content</p></PublicShell>);
    expect(screen.getByRole('link', { name: /skip to main content/i })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Emergency Alerts' }).length).toBeGreaterThan(0);
    expect(screen.getByText(/In an emergency call 112/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /report emergency/i })); expect(onReport).toHaveBeenCalled();
    const menu = screen.getByRole('button', { name: /open navigation/i });
    expect(menu).toHaveAttribute('aria-expanded', 'false'); await userEvent.click(menu); expect(screen.getByRole('button', { name: /close navigation/i })).toHaveAttribute('aria-expanded', 'true');
  });
  it('contains no operational console controls', () => {
    render(<PublicShell sections={sections} activePage="Home" onNavigate={() => {}} user={null} onSignIn={() => {}} onSignOut={() => {}} onReport={() => {}}>x</PublicShell>);
    expect(screen.queryByText(/Rescue Operations|AI Supervisor|Admin Console|Dispatch/)).toBeNull();
  });
});

describe('ConsoleShell', () => {
  it('collapses the sidebar and remembers the choice in this browser only', async () => {
    const { container } = render(<ConsoleShell sections={[{ title: 'Command', pages: ['Overview'] }]} activePage="Overview" onNavigate={() => {}} user={null} backendStatus="Connected" refreshing={false} onRefresh={() => {}} onSignOut={() => {}}>page</ConsoleShell>);
    const shell = container.querySelector('[data-shell="console"]')!;
    expect(shell.className).not.toMatch(/sidebar-collapsed/);
    await userEvent.click(screen.getByRole('button', { name: /collapse sidebar/i }));
    expect(shell.className).toMatch(/sidebar-collapsed/); expect(localStorage.getItem('rescuenet.sidebar.collapsed')).toBe('1');
    expect(screen.getByRole('link', { name: /skip to main content/i })).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
  });
  it('shows the report action only when the workspace has a report page', () => {
    const { rerender } = render(<ConsoleShell sections={[]} activePage="Overview" onNavigate={() => {}} user={null} backendStatus="Connected" refreshing={false} onRefresh={() => {}} onSignOut={() => {}}>x</ConsoleShell>);
    expect(screen.queryByRole('button', { name: /report emergency/i })).toBeNull();
    rerender(<ConsoleShell sections={[]} activePage="Overview" onNavigate={() => {}} user={null} backendStatus="Connected" refreshing={false} onRefresh={() => {}} onReport={() => {}} onSignOut={() => {}}>x</ConsoleShell>);
    expect(screen.getByRole('button', { name: /report emergency/i })).toBeInTheDocument();
  });
});

describe('route problems', () => {
  it('unauthorized and not-found screens reveal nothing about the page', () => {
    const { container, rerender } = render(<UnauthorizedPage signedIn onHome={() => {}} onSignIn={() => {}} />);
    expect(screen.getByRole('alert')).toHaveTextContent(/do not have access/i);
    expect(container.textContent).not.toMatch(/dispatch|incident|operations/i);
    rerender(<NotFoundPage onHome={() => {}} />); expect(screen.getByRole('alert')).toHaveTextContent(/not found/i);
  });
});

describe('DataNotice and ReportReceipt', () => {
  it('counts simulated records and stays silent when there are none', () => {
    const { container, rerender } = render(<DataNotice items={[{ data_label: 'SIMULATED' }, { data_label: 'SIMULATED' }, {}]} noun="incidents" />);
    expect(container.textContent).toMatch(/2 of 3 incidents are simulated/);
    rerender(<DataNotice items={[{}, { data_label: 'ENTERED' }]} noun="incidents" />); expect(container.textContent).toBe('');
  });
  it('the receipt shows the server-issued reference and code, offers copy and save, and says what to do if copying is blocked', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('blocked')) } });
    render(<ReportReceipt receipt={{ ref: 'RN-1111-2222-3333', code: 'CODE-ABC-123', warnings: [] }} onClose={() => {}} />);
    expect(screen.getByText('RN-1111-2222-3333')).toBeInTheDocument(); expect(screen.getByText('CODE-ABC-123')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /copy reference and code/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/blocked copying/i);
    expect(screen.getByRole('button', { name: /save as text file/i })).toBeInTheDocument();
  });
});
