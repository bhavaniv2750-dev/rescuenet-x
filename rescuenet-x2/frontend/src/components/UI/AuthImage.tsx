import { useEffect, useState } from 'react';
import { api } from '../../api/client';

/** Shows a private evidence photo. The browser cannot attach a sign-in token to a plain <img>, so the photo is
 *  fetched with the token and shown from a temporary local URL. Nothing is cached by the server (no-store). */
export const AuthImage: React.FC<{ src: string; alt: string; style?: React.CSSProperties }> = ({ src, alt, style }) => {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    setUrl(null);
    setFailed(false);
    api
      .getEvidenceBlob(src)
      .then((blob) => {
        if (cancelled) return;
        revoked = URL.createObjectURL(blob);
        setUrl(revoked);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [src]);

  if (failed) {
    return <div style={{ padding: '24px', color: '#64748b', fontSize: '13px' }}>The attached photo could not be loaded, or you are not allowed to view it.</div>;
  }
  if (!url) return <div style={{ padding: '24px', color: '#64748b', fontSize: '13px' }}>Loading photo…</div>;
  return <img src={url} alt={alt} style={style} />;
};
