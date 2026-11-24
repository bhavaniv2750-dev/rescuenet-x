import React, { useState } from 'react';
import { Menu, Phone, Radio, Siren, X } from 'lucide-react';
import type { AuthUser } from '../../api/types';
import type { NavSection, Page } from '../../auth/access';
import { UserMenu } from './UserMenu';

interface Props {
  sections: NavSection[];
  activePage: Page;
  onNavigate: (page: Page) => void;
  user: AuthUser | null;
  onSignIn: () => void;
  onSignOut: () => void;
  onReport: () => void;
  badges?: Partial<Record<Page, number>>;
  banner?: React.ReactNode;
  children: React.ReactNode;
}

/** Public Emergency & Community Portal shell: mobile-first, simple header navigation, a constant emergency-report action and a
 *  footer with emergency numbers. Contains no operational controls. The entries come from the server's workspace. */
export const PublicShell: React.FC<Props> = ({ sections, activePage, onNavigate, user, onSignIn, onSignOut, onReport, badges = {}, banner, children }) => {
  const [open, setOpen] = useState(false);
  const pages = sections.flatMap((s) => s.pages).filter((p) => p !== 'Report Emergency');
  const go = (p: Page) => { setOpen(false); onNavigate(p); };
  return (
    <div className="pub-shell" data-shell="public">
      <a className="rn-skip" href="#main">Skip to main content</a>
      <header className="pub-header">
        <div className="pub-header-inner">
          <button className="pub-brand" onClick={() => go(pages[0])} aria-label="RescueNet X 2.0, go to the start page">
            <span className="auth-logo" aria-hidden="true"><Radio size={18} /></span>
            <span className="pub-brand-name">RescueNet <b>X 2.0</b></span>
          </button>
          <nav className="pub-nav" aria-label="Main navigation" data-open={open}>
            {pages.map((p) => (
              <button key={p} className={`pub-nav-btn${activePage === p ? ' pub-nav-active' : ''}`} aria-current={activePage === p ? 'page' : undefined} onClick={() => go(p)}>
                <span className="nav-label">{p}</span>
                {badges[p] ? <span className="nav-badge">{badges[p]}</span> : null}
              </button>
            ))}
          </nav>
          <div className="pub-actions">
            <button className="pub-report" onClick={() => { setOpen(false); onReport(); }}><Siren size={16} aria-hidden="true" /> <span>Report emergency</span></button>
            <UserMenu user={user} onOpenAccount={() => go('My Account')} onSignOut={onSignOut} onSignIn={onSignIn} />
            <button className="pub-menu-btn" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label={open ? 'Close navigation' : 'Open navigation'}>
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </header>
      {banner}
      <main id="main" className="pub-main" tabIndex={-1}>{children}</main>
      <footer className="pub-footer">
        <div className="pub-footer-inner">
          <p><Phone size={14} aria-hidden="true" /> <strong>In an emergency call 112.</strong> Police 100 · Fire 101 · Ambulance 108. This website does not replace calling the emergency services.</p>
          <p className="rn-field-hint">RescueNet X 2.0 is a student-built prototype using simulated and public datasets. It is not an official warning service.</p>
        </div>
      </footer>
    </div>
  );
};
