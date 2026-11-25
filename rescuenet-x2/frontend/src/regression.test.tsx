import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PublicShell } from './components/Layout/PublicShell';
import { ThemeMenu } from './components/ui/ThemeMenu';
import type { NavSection } from './auth/access';

vi.mock('./api/client', () => ({ api: {}, refreshSession: vi.fn(), tokenStore: { get: () => null, set: vi.fn(), clear: vi.fn() }, UNAUTHORIZED_EVENT: 'rn-unauthorized' }));
beforeEach(() => { try { localStorage.clear(); } catch { /* ignore */ } window.matchMedia = ((q: string) => ({ matches: q.includes('dark'), media: q, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, onchange: null, dispatchEvent: () => false })) as any; });

const css = ['design/tokens.css', 'design/shell.css', 'design/ui.css', 'index.css', 'theme.css', 'App.css'].map((f) => readFileSync(join(__dirname, f), 'utf8')).join('\n').replace(/\/\*[\s\S]*?\*\//g, '');
const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ sel: m[1].trim(), body: m[2] }));

describe('Overview map-card collision (regression)', () => {
  it('no stylesheet positions an Overview class absolutely or fixed', () => {
    const jsx = readFileSync(join(__dirname, 'components/Views/OverviewView.tsx'), 'utf8');
    const used = new Set([...jsx.matchAll(/className="([^"]+)"/g)].flatMap((m) => m[1].split(/\s+/)));
    const offenders = rules.filter((r) => /position:\s*(absolute|fixed)/.test(r.body)).flatMap((r) => r.sel.split(',').map((s) => s.trim()))
      .filter((s) => /^\.[\w-]+$/.test(s) && used.has(s.slice(1)) && s !== '.rn-sr');   // .rn-sr is the screen-reader-only utility
    expect(offenders).toEqual([]);   // e.g. the old `.map-card { position: absolute }` info card pulled the whole Overview map out of its grid cell
  });
  it('the Overview grid places forecast and map in columns and lets cells shrink', () => {
    const g = rules.find((r) => r.sel === '.overview-main-grid' && /grid-template-columns:\s*minmax/.test(r.body));
    expect(g).toBeTruthy();
    expect(rules.some((r) => r.sel === '.overview-main-grid > *' && /min-width:\s*0/.test(r.body))).toBe(true);
  });
});

describe('Map stacking (regression: Leaflet controls above the mobile drawer)', () => {
  it('the map frame is an isolated stacking context', () => {
    expect(rules.some((r) => r.sel.split(',').map((s) => s.trim()).includes('.rn-map-frame') && /isolation:\s*isolate/.test(r.body))).toBe(true);
  });
  it('no rule gives a header, drawer or dropdown a z-index of 1000 or more', () => {
    const bad = rules.filter((r) => /^\.(pub-header|app-sidebar|sidebar-backdrop|app-topbar|theme-menu-pop|pub-nav)\b/.test(r.sel)).filter((r) => { const z = /z-index:\s*(\d+)/.exec(r.body); return z && Number(z[1]) >= 1000; });
    expect(bad).toEqual([]);
  });
});

const sections: NavSection[] = [{ title: 'Flood watch', pages: ['Home', 'Emergency Alerts'] }];
describe('Public mobile navigation drawer', () => {
  const shell = (onNavigate = vi.fn()) => render(<PublicShell sections={sections} activePage="Home" onNavigate={onNavigate} user={null} onSignIn={() => {}} onSignOut={() => {}} onReport={() => {}}><p>content</p></PublicShell>);
  it('opens with a labelled trigger, closes with Escape and returns focus to the trigger', async () => {
    shell(); const t = screen.getByRole('button', { name: /open navigation/i });
    await userEvent.click(t); expect(screen.getByRole('button', { name: /close navigation/i })).toHaveAttribute('aria-expanded', 'true');
    await userEvent.keyboard('{Escape}'); expect(screen.getByRole('button', { name: /open navigation/i })).toHaveAttribute('aria-expanded', 'false'); expect(document.activeElement).toBe(t);
  });
  it('closes after navigating', async () => {
    const nav = vi.fn(); shell(nav); await userEvent.click(screen.getByRole('button', { name: /open navigation/i }));
    await userEvent.click(screen.getByRole('button', { name: /emergency alerts/i })); expect(nav).toHaveBeenCalledWith('Emergency Alerts');
    expect(screen.getByRole('button', { name: /open navigation/i })).toHaveAttribute('aria-expanded', 'false');
  });
  it('has exactly one theme control in the header (an icon, not three buttons)', () => {
    shell(); expect(screen.getAllByRole('button', { name: /theme/i })).toHaveLength(1); expect(screen.queryByRole('radiogroup')).toBeNull();
  });
});

describe('ThemeMenu', () => {
  it('shows a check beside the selected option and updates the trigger icon label', async () => {
    const { initTheme } = await import('./lib/theme'); initTheme();
    render(<ThemeMenu />);
    expect(screen.getByRole('button', { name: /theme: system default/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /theme:/i }));
    const items = screen.getAllByRole('menuitemradio'); expect(items.map((i) => i.textContent)).toEqual(['Light', 'Dark', 'System default']);
    expect(items[2]).toHaveAttribute('aria-checked', 'true'); expect(items[2].querySelector('svg.theme-menu-check')).toBeTruthy(); expect(items[0].querySelector('svg.theme-menu-check')).toBeNull();
    await userEvent.click(items[1]); expect(document.documentElement.dataset.theme).toBe('dark'); expect(screen.getByRole('button', { name: /theme: dark/i })).toBeInTheDocument();
    expect(screen.queryByRole('menu')).toBeNull();
  });
  it('follows a change made in another tab', async () => {
    const { initTheme } = await import('./lib/theme'); initTheme(); render(<ThemeMenu />);
    localStorage.setItem('rescuenet.theme', 'light'); window.dispatchEvent(new StorageEvent('storage', { key: 'rescuenet.theme', newValue: 'light' }));
    expect(await screen.findByRole('button', { name: /theme: light/i })).toBeInTheDocument(); expect(document.documentElement.dataset.theme).toBe('light');
  });
});
