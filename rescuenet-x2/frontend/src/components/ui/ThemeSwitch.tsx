import React from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme, type AppTheme } from '../../lib/theme';

const OPTIONS: { id: AppTheme; label: string; Icon: typeof Sun }[] = [
  { id: 'system', label: 'System', Icon: Monitor },
  { id: 'light', label: 'Light', Icon: Sun },
  { id: 'dark', label: 'Dark', Icon: Moon },
];

/** Three-way application theme control (System / Light / Dark). The map has its own appearance control in the map panel. */
export const ThemeSwitch: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { app, setAppTheme } = useTheme();
  return (
    <div className={`theme-switch ${className}`} role="radiogroup" aria-label="Application theme">
      {OPTIONS.map(({ id, label, Icon }) => (
        <button key={id} type="button" role="radio" aria-checked={app === id} className={`theme-switch-btn${app === id ? ' on' : ''}`} onClick={() => setAppTheme(id)} title={`${label} theme`}>
          <Icon size={14} aria-hidden="true" /><span className="theme-switch-label">{label}</span>
        </button>
      ))}
    </div>
  );
};
