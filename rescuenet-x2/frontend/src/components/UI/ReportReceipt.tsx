export interface ReportReceiptData {
  ref: string;
  code: string;
  warnings: string[];
}

/** Shown after a report is sent. The tracking code exists only here: the server keeps just a hash of it, so the
 *  panel stays on screen (across page changes) until the person confirms they have saved it. */
export const ReportReceipt: React.FC<{ receipt: ReportReceiptData; onClose: () => void }> = ({ receipt, onClose }) => (
  <div className="panel" role="status" aria-live="polite" style={{ margin: '0 0 16px', border: '1px solid #22c55e' }}>
    <h3 style={{ marginTop: 0 }}>Report received. Keep these to follow it</h3>
    <p style={{ margin: '4px 0' }}>
      Reference: <strong style={{ fontFamily: 'monospace', fontSize: '18px' }}>{receipt.ref}</strong>
    </p>
    <p style={{ margin: '4px 0' }}>
      Tracking code: <strong style={{ fontFamily: 'monospace', fontSize: '18px' }}>{receipt.code}</strong>
    </p>
    <p className="text-xs text-muted" style={{ margin: '8px 0' }}>
      The tracking code is shown only once and cannot be recovered. Without it, nobody else can see your report's status.
      This is not an emergency line: if you are in immediate danger, call 112.
    </p>
    {receipt.warnings.length > 0 && <p className="text-xs text-orange">Your report was saved, but: {receipt.warnings.join(' ')}</p>}
    <button className="btn-secondary" onClick={() => navigator.clipboard?.writeText(`${receipt.ref}  ${receipt.code}`)}>
      Copy reference and code
    </button>{' '}
    <button className="btn-secondary" onClick={onClose}>
      I have saved them
    </button>
  </div>
);
