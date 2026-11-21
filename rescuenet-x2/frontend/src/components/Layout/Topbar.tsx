import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, LogIn, LogOut, Menu, RefreshCw, Siren, UserCircle } from 'lucide-react';
import type { AuthUser } from '../../api/types';
import { ROLE_LABEL } from '../../auth/access';

interface TopbarProps {
  activePage: string;
  user: AuthUser | null;
  onToggleSidebar: () => void;
  onRefresh: () => void;
  onReport: () => void;
  onOpenAccount: () => void;
  onSignIn: () => void;
  onSignOut: () => void;
  refreshing: boolean;
  backendStatus: string;
}

export const Topbar: React.FC<TopbarProps> = ({
  activePage, user, onToggleSidebar, onRefresh, onReport, onOpenAccount, onSignIn, onSignOut, refreshing, backendStatus,
}) => {
  const online = backendStatus === 'Connected';
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', esc);
    };
  }, [menuOpen]);

  const initials = user ? user.full_name.split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase() : '';

  return (
    <header className="app-topbar">
      <div className="topbar-left">
        <button className="menu-toggle-btn" onClick={onToggleSidebar} aria-label="Toggle navigation">
          <Menu size={20} />
        </button>
        <div className="breadcrumbs">
          <span className="text-muted hide-sm">RescueNet</span>
          <span className="breadcrumb-slash hide-sm">/</span>
          <strong className="breadcrumb-current">{activePage}</strong>
        </div>
      </div>

      <div className="topbar-right">
        <div className="live-data-indicator hide-sm" title="Data refreshes from the server every 15 seconds">
          <span className={`status-dot ${online ? 'dot-green' : 'dot-red'}`} />
          <span>{online ? 'Server connected' : backendStatus}</span>
        </div>

        <button className="btn-icon" onClick={onRefresh} disabled={refreshing} title="Refresh data now" aria-label="Refresh data">
          <RefreshCw size={16} className={refreshing ? 'spin' : ''} />
        </button>

        <button className="btn-danger-soft btn-sm" onClick={onReport}>
          <Siren size={14} /> <span className="hide-xs">Report emergency</span>
        </button>

        {user ? (
          <div className="user-menu" ref={menuRef}>
            <button className="user-chip" onClick={() => setMenuOpen((v) => !v)} aria-haspopup="menu" aria-expanded={menuOpen}>
              <span className="avatar">{initials}</span>
              <span className="user-chip-text hide-sm">
                <strong>{user.full_name}</strong>
                <small>{ROLE_LABEL[user.role]}</small>
              </span>
              <ChevronDown size={14} />
            </button>
            {menuOpen && (
              <div className="user-dropdown" role="menu">
                <div className="user-dropdown-head">
                  <strong>{user.full_name}</strong>
                  <small>{ROLE_LABEL[user.role]} · {user.username}</small>
                </div>
                <button role="menuitem" onClick={() => { setMenuOpen(false); onOpenAccount(); }}>
                  <UserCircle size={15} /> My account
                </button>
                <button role="menuitem" onClick={() => { setMenuOpen(false); onSignOut(); }}>
                  <LogOut size={15} /> Sign out
                </button>
              </div>
            )}
          </div>
        ) : (
          <button className="btn-primary btn-sm" onClick={onSignIn}>
            <LogIn size={14} /> Sign in
          </button>
        )}
      </div>
    </header>
  );
};
