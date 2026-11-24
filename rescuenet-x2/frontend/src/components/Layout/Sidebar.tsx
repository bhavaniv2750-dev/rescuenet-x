import React from 'react';
import {
  LayoutDashboard, Layers, Activity, Bell, LifeBuoy, Users, Building2, FilePlus, Award, Bot, Database,
  Settings, Radio, Home, ClipboardList, Siren, UserCircle, ShieldCheck, ScrollText, Truck, Landmark,
} from 'lucide-react';
import type { NavSection, Page } from '../../auth/access';

interface SidebarProps {
  sections: NavSection[];
  activePage: string;
  onNavigate: (page: Page) => void;
  isOpen: boolean;
  onClose: () => void;
  backendStatus: string;
  badges: Partial<Record<Page, number>>;
}

const ICONS: Record<Page, React.ElementType> = {
  Home, Overview: LayoutDashboard, 'Flood Digital Twin': Layers, 'Flood Forecasting': Activity,
  'Emergency Alerts': Bell, 'Rescue Operations': LifeBuoy, 'My Missions': Truck,
  'Volunteer Coordination': Users, 'Facilities & Shelters': Building2, 'Incident Reports': FilePlus,
  'Report Emergency': Siren, 'My Reports': ClipboardList, 'Rescue Records': Award, 'AI Supervisor': Bot,
  'Data & Models': Database, Diagnostics: Radio, 'Admin Console': ShieldCheck, 'Agencies & Invitations': Landmark, 'Audit Log': ScrollText, Settings, 'My Account': UserCircle,
};

export const Sidebar: React.FC<SidebarProps> = ({ sections, activePage, onNavigate, isOpen, onClose, backendStatus, badges }) => {
  return (
    <>
      {isOpen && <div className="sidebar-backdrop" onClick={onClose} />}

      <aside className={`app-sidebar ${isOpen ? 'sidebar-open' : ''}`} aria-label="Main navigation">
        <div className="brand-section">
          <div className="brand-badge">
            <Radio size={20} className="pulse" />
          </div>
          <div className="brand-copy">
            <div className="brand-name">
              RESCUENET <span className="text-cyan">X 2.0</span>
            </div>
            <div className="brand-sub">FLOOD DIGITAL TWIN</div>
          </div>
        </div>

        <div className="sidebar-scroll">
          {sections.map((section) => (
            <div key={section.title} className="nav-section">
              <div className="nav-group-title">{section.title.toUpperCase()}</div>
              <nav className="nav-items-list">
                {section.pages.map((page) => {
                  const Icon = ICONS[page] || Settings;
                  const count = badges[page];
                  const isActive = activePage === page;
                  return (
                    <button
                      key={page}
                      title={page}
                      className={`nav-button ${isActive ? 'nav-active' : ''}`}
                      aria-current={isActive ? 'page' : undefined}
                      onClick={() => {
                        onNavigate(page);
                        onClose();
                      }}
                    >
                      <Icon size={18} className="nav-icon" />
                      <span className="nav-label">{page}</span>
                      {count ? <span className="nav-badge">{count}</span> : null}
                    </button>
                  );
                })}
              </nav>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="status-connection-card">
            <div className="status-indicator">
              <span className={`status-dot ${backendStatus === 'Connected' ? 'dot-green' : 'dot-red'}`} />
              <div className="status-copy">
                <strong>Server</strong>
                <span>{backendStatus === 'Connected' ? 'Connected' : backendStatus}</span>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};
