import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, LogIn, LogOut, UserCircle } from 'lucide-react';
import type { AuthUser } from '../../api/types';
import { ROLE_LABEL } from '../../auth/access';

/** Account menu shared by both shells: profile and security (My Account) and sign out, or Sign in for guests. */
export const UserMenu: React.FC<{ user: AuthUser | null; onOpenAccount: () => void; onSignOut: () => void; onSignIn: () => void }> = ({ user, onOpenAccount, onSignOut, onSignIn }) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => { if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false); };
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false);
    document.addEventListener('mousedown', close); document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [menuOpen]);
  if (!user) return <button className="btn-primary btn-sm" onClick={onSignIn}><LogIn size={14} /> Sign in</button>;
  const initials = user.full_name.split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase();
  return (
    <div className="user-menu" ref={menuRef}>
      <button className="user-chip" onClick={() => setMenuOpen((v) => !v)} aria-haspopup="menu" aria-expanded={menuOpen} aria-label={`Account menu for ${user.full_name}`}>
        <span className="avatar" aria-hidden="true">{initials}</span>
        <span className="user-chip-text hide-sm"><strong>{user.full_name}</strong><small>{ROLE_LABEL[user.role]}</small></span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {menuOpen && (
        <div className="user-dropdown" role="menu">
          <div className="user-dropdown-head"><strong>{user.full_name}</strong><small>{ROLE_LABEL[user.role]} · {user.username}</small></div>
          <button role="menuitem" onClick={() => { setMenuOpen(false); onOpenAccount(); }}><UserCircle size={15} /> My account and security</button>
          <button role="menuitem" onClick={() => { setMenuOpen(false); onSignOut(); }}><LogOut size={15} /> Sign out</button>
        </div>
      )}
    </div>
  );
};
