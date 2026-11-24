import React, { useEffect, useState } from 'react';
import type { AuthUser } from '../../api/types';
import type { NavSection, Page } from '../../auth/access';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';

interface Props {
  sections: NavSection[];
  activePage: Page;
  onNavigate: (page: Page) => void;
  user: AuthUser | null;
  backendStatus: string;
  refreshing: boolean;
  onRefresh: () => void;
  onReport?: () => void;
  onSignOut: () => void;
  badges?: Partial<Record<Page, number>>;
  status?: React.ReactNode;
  children: React.ReactNode;
}

const KEY = 'rescuenet.sidebar.collapsed';

/** Professional Emergency Operations Console shell: collapsible sidebar (the choice is remembered in this browser only), operational status in
 *  the top bar, desktop-first and information-dense, responsive down to a drawer on small screens. Entries come from the server's workspace. */
export const ConsoleShell: React.FC<Props> = ({ sections, activePage, onNavigate, user, backendStatus, refreshing, onRefresh, onReport, onSignOut, badges = {}, status, children }) => {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<boolean>(() => { try { return localStorage.getItem(KEY) === '1'; } catch { return false; } });
  useEffect(() => { try { localStorage.setItem(KEY, collapsed ? '1' : '0'); } catch { /* optional convenience */ } }, [collapsed]);
  return (
    <div className={`app-shell${collapsed ? ' sidebar-collapsed' : ''}`} data-shell="console">
      <a className="rn-skip" href="#main">Skip to main content</a>
      <Sidebar sections={sections} activePage={activePage} onNavigate={onNavigate} isOpen={open} onClose={() => setOpen(false)} backendStatus={backendStatus} badges={badges} />
      <div className="app-main">
        <Topbar activePage={activePage} user={user} onToggleSidebar={() => setOpen((v) => !v)} collapsed={collapsed} onToggleCollapse={() => setCollapsed((v) => !v)}
          onRefresh={onRefresh} onReport={onReport} onOpenAccount={() => onNavigate('My Account')} onSignIn={() => undefined} onSignOut={onSignOut} refreshing={refreshing} backendStatus={backendStatus} status={status} />
        <main id="main" className="page-viewport" tabIndex={-1} key={activePage}>{children}</main>
      </div>
    </div>
  );
};
