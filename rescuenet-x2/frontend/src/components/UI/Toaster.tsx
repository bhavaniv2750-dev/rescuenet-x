import React, { useEffect, useState } from 'react';
import { CheckCircle2, Info, X, XCircle } from 'lucide-react';
import { TOAST_EVENT } from '../../lib/toast';
import type { ToastMessage } from '../../lib/toast';

const ICONS = { success: CheckCircle2, error: XCircle, info: Info };

/** Small, non-blocking messages for the result of an action. They disappear on their own. */
export const Toaster: React.FC = () => {
  const [items, setItems] = useState<ToastMessage[]>([]);

  useEffect(() => {
    const onToast = (e: Event) => {
      const t = (e as CustomEvent<ToastMessage>).detail;
      setItems((prev) => [...prev.slice(-3), t]);
      window.setTimeout(() => setItems((prev) => prev.filter((x) => x.id !== t.id)), t.kind === 'error' ? 7000 : 4000);
    };
    window.addEventListener(TOAST_EVENT, onToast);
    return () => window.removeEventListener(TOAST_EVENT, onToast);
  }, []);

  return (
    <div className="toaster" role="status" aria-live="polite">
      {items.map((t) => {
        const Icon = ICONS[t.kind];
        return (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            <Icon size={16} />
            <span>{t.text}</span>
            <button aria-label="Dismiss message" onClick={() => setItems((p) => p.filter((x) => x.id !== t.id))}>
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
};
