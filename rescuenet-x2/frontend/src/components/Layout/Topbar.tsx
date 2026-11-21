import React from 'react';
import { Menu, RefreshCw, Plus, MapPin } from 'lucide-react';

interface TopbarProps {
  activePage: string;
  onToggleSidebar: () => void;
  onRefresh: () => void;
  onOpenReportModal: () => void;
  refreshing: boolean;
  backendStatus: string;
}

export const Topbar: React.FC<TopbarProps> = ({
  activePage,
  onToggleSidebar,
  onRefresh,
  onOpenReportModal,
  refreshing,
  backendStatus,
}) => {
  const online = backendStatus === 'Connected';
  return (
    <header className="app-topbar">
      <div className="topbar-left">
        <button className="menu-toggle-btn" onClick={onToggleSidebar} aria-label="Toggle navigation">
          <Menu size={20} />
        </button>

        <div className="breadcrumbs">
          <span className="text-muted">RescueNet</span>
          <span className="breadcrumb-slash">/</span>
          <strong className="breadcrumb-current">{activePage}</strong>
        </div>
      </div>

      <div className="topbar-right">
        {/* Region Tag */}
        <div className="region-indicator">
          <MapPin size={14} className="text-cyan" />
          <span>Bengaluru, Karnataka</span>
        </div>

        {/* Backend connection (data is polled every 15 s; there is no live sensor feed) */}
        <div className="live-data-indicator" title="Data refreshes from the backend every 15 seconds">
          <span className={`status-dot ${online ? 'dot-green' : 'dot-red'}`} />
          <span>{online ? 'Backend connected' : backendStatus}</span>
        </div>

        {/* Refresh Action Button */}
        <button
          className="btn-icon"
          onClick={onRefresh}
          disabled={refreshing}
          title="Refresh data now"
        >
          <RefreshCw size={16} className={refreshing ? 'spin' : ''} />
        </button>

        {/* Quick Report Button */}
        <button className="btn-primary btn-sm" onClick={onOpenReportModal}>
          <Plus size={14} /> Report Incident
        </button>
      </div>
    </header>
  );
};
