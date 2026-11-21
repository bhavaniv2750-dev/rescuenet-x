import React from 'react';
import {
  LayoutDashboard,
  Layers,
  Activity,
  Bell,
  LifeBuoy,
  Users,
  Building2,
  FilePlus,
  Award,
  Bot,
  Database,
  Settings,
  Radio,
} from 'lucide-react';

interface SidebarProps {
  activePage: string;
  onNavigate: (page: string) => void;
  isOpen: boolean;
  onClose: () => void;
  backendStatus: string;
  incidentCount: number;
  activeAlertCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activePage,
  onNavigate,
  isOpen,
  onClose,
  backendStatus,
  incidentCount,
  activeAlertCount,
}) => {
  const navItems = [
    { name: 'Overview', icon: LayoutDashboard, count: null },
    { name: 'Flood Digital Twin', icon: Layers, count: null },
    { name: 'Flood Forecasting', icon: Activity, count: null },
    { name: 'Emergency Alerts', icon: Bell, count: activeAlertCount > 0 ? activeAlertCount : null },
    { name: 'Rescue Operations', icon: LifeBuoy, count: incidentCount > 0 ? incidentCount : null },
    { name: 'Volunteer Coordination', icon: Users, count: null },
    { name: 'Facilities & Shelters', icon: Building2, count: null },
    { name: 'Incident Reports', icon: FilePlus, count: null },
    { name: 'Rescue Records', icon: Award, count: null },
    { name: 'AI Supervisor', icon: Bot, count: null },
    { name: 'Data & Models', icon: Database, count: null },
    { name: 'Settings', icon: Settings, count: null },
  ];

  return (
    <>
      {isOpen && <div className="sidebar-backdrop" onClick={onClose} />}

      <aside className={`app-sidebar ${isOpen ? 'sidebar-open' : ''}`}>
        {/* Brand Header */}
        <div className="brand-section">
          <div className="brand-badge">
            <Radio size={20} className="pulse" />
          </div>
          <div className="brand-copy">
            <div className="brand-name">
              RESCUENET <span className="text-cyan">X 2.0</span>
            </div>
            <div className="brand-sub">FLOOD DIGITAL TWIN · AI OPS</div>
          </div>
        </div>

        {/* Navigation list */}
        <div className="sidebar-scroll">
          <div className="nav-group-title">COMMAND MODULES</div>
          <nav className="nav-items-list">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activePage === item.name;

              return (
                <button
                  key={item.name}
                  className={`nav-button ${isActive ? 'nav-active' : ''}`}
                  onClick={() => {
                    onNavigate(item.name);
                    onClose();
                  }}
                >
                  <Icon size={18} className="nav-icon" />
                  <span className="nav-label">{item.name}</span>
                  {item.count !== null && (
                    <span className="nav-badge">{item.count}</span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Sidebar Footer Connection Status */}
        <div className="sidebar-footer">
          <div className="status-connection-card">
            <div className="status-indicator">
              <span className={`status-dot ${backendStatus === 'Connected' ? 'dot-green' : 'dot-red'}`} />
              <div className="status-copy">
                <strong>FastAPI Core</strong>
                <span>{backendStatus}</span>
              </div>
            </div>
            <span className="port-badge">:8000</span>
          </div>
          <div className="system-version-text">RESCUENET X 2.0 · FULL-STACK BUILD</div>
        </div>
      </aside>
    </>
  );
};
