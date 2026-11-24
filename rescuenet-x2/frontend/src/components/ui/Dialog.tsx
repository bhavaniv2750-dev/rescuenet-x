import { X } from 'lucide-react';
import { useEffect, useId, useRef } from 'react';
import { Button } from './Button';

interface DialogProps { open: boolean; title: string; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode; width?: number }
/** Modal dialog: focus moves in, Escape closes, Tab is kept inside, focus returns to the opener. */
export const Dialog: React.FC<DialogProps> = ({ open, title, onClose, children, footer, width = 480 }) => {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    const node = ref.current;
    const focusables = () => Array.from(node?.querySelectorAll<HTMLElement>('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])') ?? []).filter((e) => !e.hasAttribute('disabled'));
    (focusables()[1] ?? focusables()[0])?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose(); }
      if (e.key === 'Tab') {
        const f = focusables(); if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); opener?.focus?.(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="rn-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="rn-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={ref} style={{ maxWidth: width }}>
        <div className="rn-dialog-head">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="rn-icon-btn" onClick={onClose} aria-label="Close dialog"><X size={18} /></button>
        </div>
        <div className="rn-dialog-body">{children}</div>
        {footer ? <div className="rn-dialog-foot">{footer}</div> : null}
      </div>
    </div>
  );
};

interface ConfirmProps { open: boolean; title: string; message: React.ReactNode; confirmLabel?: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onCancel: () => void }
/** Confirmation for consequential actions. The confirm button names the action; nothing happens on open. */
export const ConfirmDialog: React.FC<ConfirmProps> = ({ open, title, message, confirmLabel = 'Confirm', danger, busy, onConfirm, onCancel }) => (
  <Dialog open={open} title={title} onClose={onCancel}
    footer={<><Button onClick={onCancel}>Cancel</Button><Button variant={danger ? 'danger' : 'primary'} loading={busy} onClick={onConfirm}>{confirmLabel}</Button></>}>
    <div className="rn-confirm-msg">{message}</div>
  </Dialog>
);
