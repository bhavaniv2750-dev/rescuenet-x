import React from 'react';
import { Menu, PanelLeftClose, PanelLeftOpen, RefreshCw, Siren } from 'lucide-react';
import type { AuthUser } from '../../api/types';
import { UserMenu } from './UserMenu';

interface TopbarProps {
  activePage: string;
  user: AuthUser | null;
  onToggleSidebar: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  onRefresh: () => void;
  /** Omitted when this account has no emergency-report page in its workspace. */
  onReport?: () => void;
  status?: React.ReactNode;
  onOpenAccount: () => void;
  onSignIn: () => void;
  onSignOut: () => void;
  refreshing: boolean;
  backendStatus: string;
}

export const Topbar: React.FC<TopbarProps> = ({
  activePage, user, onToggleSidebar, collapsed, onToggleCollapse, status, onRefresh, onReport, onOpenAccount, onSignIn, onSignOut, refreshing, backendStatus,
}) => {
  const online = backendStatus === 'Connected';
  return (
    <header className="app-topbar">
      <div className="topbar-left">
        <button className="menu-toggle-btn" onClick={onToggleSidebar} aria-label="Open navigation">
          <Menu size={20} />
        </button>
        {onToggleCollapse && (
          <button className="collapse-btn" onClick={onToggleCollapse} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-pressed={Boolean(collapsed)} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        )}
        <div className="breadcrumbs">
          <span className="text-muted hide-sm">RescueNet</span>
          <span className="breadcrumb-slash hide-sm">/</span>
          <strong className="breadcrumb-current">{activePage}</strong>
        </div>
      </div>

      <div className="topbar-right">
        {status}
        <div className="live-data-indicator hide-sm" title="Data refreshes from the server every 15 seconds">
          <span className={`status-dot ${online ? 'dot-green' : 'dot-red'}`} />
          <span>{online ? 'Server connected' : backendStatus}</span>
        </div>

        <button className="btn-icon" onClick={onRefresh} disabled={refreshing} title="Refresh data now" aria-label="Refresh data">
          <RefreshCw size={16} className={refreshing ? 'spin' : ''} />
        </button>

        {onReport && (
          <button className="btn-danger-soft btn-sm" onClick={onReport}>
            <Siren size={14} /> <span className="hide-xs">Report emergency</span>
          </button>
        )}

        <UserMenu user={user} onOpenAccount={onOpenAccount} onSignOut={onSignOut} onSignIn={onSignIn} />
      </div>
    </header>
  );
};
