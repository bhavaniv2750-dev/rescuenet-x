import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { Capabilities, DevOutboxMessage } from '../../api/types';

/** Development only. Shows the messages the development outbox holds (verification codes, reset links). The server returns
 *  404 for this outside development on this machine, and the panel renders nothing unless /auth/capabilities says development.
 *  NOTHING listed here was delivered to a real mailbox or phone. */
export const DevOutbox: React.FC<{ refreshKey?: number }> = ({ refreshKey = 0 }) => {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [items, setItems] = useState<DevOutboxMessage[]>([]);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    api.getCapabilities().then(setCaps).catch(() => setCaps(null));
  }, []);

  useEffect(() => {
    if (caps?.environment !== 'development') return;
    api.getDevOutbox().then((r) => { setItems(r.items.slice(0, 5)); setNotice(r.notice); }).catch(() => setItems([]));
  }, [caps, refreshKey]);

  if (caps?.environment !== 'development') return null;
  return (
    <div className="form-notice form-notice-info" style={{ marginTop: 16 }} aria-label="Development outbox">
      <strong>DEVELOPMENT OUTBOX</strong>
      <div className="text-xs">{notice || 'Nothing was delivered to any real mailbox or phone.'}</div>
      {items.length === 0 && <div className="text-xs text-muted">No messages yet.</div>}
      {items.map((m) => (
        <pre key={m.id} className="text-xs" style={{ whiteSpace: 'pre-wrap', margin: '6px 0' }}>
          {m.subject} → {m.to}{'\n'}{m.body}
        </pre>
      ))}
    </div>
  );
};
