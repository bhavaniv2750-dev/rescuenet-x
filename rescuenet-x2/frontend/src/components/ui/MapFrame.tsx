import { MapPinOff } from 'lucide-react';

/** Frame for a map: fixed accessible region, optional legend, and a clear message when base-map tiles cannot be loaded. Markers and
 *  overlays still render without tiles, so the map is never blank; the basemap itself needs internet access to OpenStreetMap. */
export const MapFrame: React.FC<{ label: string; tileError?: boolean; legend?: React.ReactNode; children: React.ReactNode; height?: string }> = ({ label, tileError, legend, children, height }) => (
  <div className="rn-map-frame" role="region" aria-label={label} style={height ? { height } : undefined}>
    {children}
    {tileError ? (
      <div className="rn-map-notice" role="status">
        <MapPinOff size={14} aria-hidden="true" /> Base map unavailable (no connection to OpenStreetMap). Overlays are still shown; positions are accurate, background tiles are missing.
      </div>
    ) : null}
    {legend ? <div className="rn-map-legend">{legend}</div> : null}
  </div>
);
