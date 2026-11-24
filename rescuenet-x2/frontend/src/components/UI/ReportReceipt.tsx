import { useState } from 'react';
import { CheckCircle2, Copy, Download } from 'lucide-react';
import { Button } from '../ui';

export interface ReportReceiptData {
  ref: string;
  code: string;
  warnings: string[];
}

/** Shown ONLY after the server confirmed the report. The tracking code exists only here: the server keeps just a hash of it, so the panel stays
 *  on screen (across page changes) until the person confirms they have saved it. */
export const ReportReceipt: React.FC<{ receipt: ReportReceiptData; onClose: () => void }> = ({ receipt, onClose }) => {
  const [copied, setCopied] = useState<'ok' | 'fail' | null>(null);
  const text = `RescueNet X report\nReference: ${receipt.ref}\nTracking code: ${receipt.code}\nKeep the code private: it is the only way to see this report's status.\n`;
  const copy = async () => {
    try { await navigator.clipboard.writeText(`${receipt.ref}  ${receipt.code}`); setCopied('ok'); } catch { setCopied('fail'); }
  };
  const save = () => {
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' })); a.download = `rescuenet-report-${receipt.ref}.txt`; a.click(); URL.revokeObjectURL(a.href);
  };
  return (
    <section className="receipt" role="status" aria-live="polite" aria-labelledby="receipt-title">
      <h2 id="receipt-title"><CheckCircle2 size={20} aria-hidden="true" /> Report received. Keep these to follow it</h2>
      <dl className="receipt-grid">
        <dt>Reference</dt><dd className="auth-mono" data-sensitive>{receipt.ref}</dd>
        <dt>Tracking code</dt><dd className="auth-mono" data-sensitive>{receipt.code}</dd>
      </dl>
      <p className="rn-field-hint">Copy the reference and code, or save them as a text file, before you close this panel. The tracking code is shown only once and cannot be recovered; without it nobody else can see your report's status. This is not an emergency line: if you are in immediate danger, call 112.</p>
      {receipt.warnings.length > 0 && <div className="auth-notice auth-notice-warn" role="alert">Your report was saved, but: {receipt.warnings.join(' ')}</div>}
      <div className="receipt-actions">
        <Button icon={<Copy size={15} />} onClick={copy}>Copy reference and code</Button>
        <Button icon={<Download size={15} />} onClick={save}>Save as text file</Button>
        <Button variant="primary" onClick={onClose}>I have saved them</Button>
      </div>
      {copied === 'ok' && <span className="rn-field-hint" role="status">Copied to the clipboard.</span>}
      {copied === 'fail' && <span className="rn-field-hint" role="alert">Your browser blocked copying. Select the text above or use "Save as text file".</span>}
    </section>
  );
};
