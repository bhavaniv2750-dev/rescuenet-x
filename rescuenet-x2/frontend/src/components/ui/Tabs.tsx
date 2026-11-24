import { useId } from 'react';

interface TabsProps<T extends string> { tabs: { id: T; label: string; count?: number }[]; value: T; onChange: (v: T) => void; label: string }
/** Accessible tab list: arrow keys move between tabs. Render the panel yourself with role="tabpanel". */
export function Tabs<T extends string>({ tabs, value, onChange, label }: TabsProps<T>) {
  const base = useId();
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const n = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : null;
    if (n === null) return;
    e.preventDefault();
    const t = tabs[(n + tabs.length) % tabs.length];
    onChange(t.id);
    document.getElementById(`${base}-${t.id}`)?.focus();
  };
  return (
    <div className="rn-tabs" role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button key={t.id} id={`${base}-${t.id}`} role="tab" type="button" aria-selected={value === t.id} tabIndex={value === t.id ? 0 : -1}
          className={`rn-tab${value === t.id ? ' rn-tab-active' : ''}`} onClick={() => onChange(t.id)} onKeyDown={(e) => onKey(e, i)}>
          {t.label}{t.count !== undefined ? <span className="rn-tab-count">{t.count}</span> : null}
        </button>
      ))}
    </div>
  );
}
