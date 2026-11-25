import React, { useEffect, useId, useRef, useState } from 'react';
import { Check, Monitor, Moon, Sun } from 'lucide-react';
import { useTheme, type AppTheme } from '../../lib/theme';

const OPTIONS: { id: AppTheme; label: string; Icon: typeof Sun }[] = [
  { id: 'light', label: 'Light', Icon: Sun },
  { id: 'dark', label: 'Dark', Icon: Moon },
  { id: 'system', label: 'System default', Icon: Monitor },
];

/** One compact icon button (sun / moon / monitor for the current choice) that opens a small menu: Light, Dark, System default, with a check
 *  beside the selected one. Same control in every header and on the sign-in screens. The map has its own appearance setting in its panel. */
export const ThemeMenu: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { app, setAppTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const id = useId();
  const Current = OPTIONS.find((o) => o.id === app)!.Icon;
  const label = OPTIONS.find((o) => o.id === app)!.label;

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', away);
    root.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
    return () => document.removeEventListener('mousedown', away);
  }, [open]);

  const key = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { setOpen(false); btn.current?.focus(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const items = Array.from(root.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? []);
      const i = items.indexOf(document.activeElement as HTMLElement);
      items[(i + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length]?.focus();
    }
  };

  return (
    <div className={`theme-menu ${className}`} ref={root} onKeyDown={key}>
      <button ref={btn} type="button" className="theme-menu-btn" aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
        aria-label={`Theme: ${label}. Change theme`} title={`Theme: ${label}`} onClick={() => setOpen((v) => !v)}>
        <Current size={18} aria-hidden="true" />
      </button>
      {open && (
        <div className="theme-menu-pop" role="menu" id={id} aria-label="Theme">
          {OPTIONS.map(({ id: o, label: l, Icon }) => (
            <button key={o} type="button" role="menuitemradio" aria-checked={app === o} className="theme-menu-item" onClick={() => { setAppTheme(o); setOpen(false); btn.current?.focus(); }}>
              <Icon size={16} aria-hidden="true" /><span>{l}</span>{app === o ? <Check size={16} className="theme-menu-check" aria-hidden="true" /> : <span className="theme-menu-check" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
