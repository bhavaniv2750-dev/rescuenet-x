import React from 'react';
import type { VisionAnalysis } from '../../api/types';

const sevColour: Record<string, string> = {
  CRITICAL: 'var(--sev-critical)',
  HIGH: '#f97316',
  MODERATE: 'var(--sev-high)',
  LOW: '#10b981',
};

/** Result card for the pretrained flood-photo models. Results are PREDICTED, never ground truth. */
export const FloodPhotoAnalysis: React.FC<{ result: Partial<VisionAnalysis>; compact?: boolean }> = ({ result, compact }) => {
  const p = result.flood_probability ?? 0;
  const row = (label: string, value: React.ReactNode) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', fontSize: '12px', padding: '2px 0' }}>
      <span className="text-muted">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
  return (
    <div style={{ padding: '10px', background: 'var(--rn-slate-1, #030712)', border: '1px solid var(--border-subtle, #1e293b)', borderRadius: '6px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <strong style={{ fontSize: '13px', color: result.flood_detected ? 'var(--rn-accent)' : 'var(--rn-text-dim)' }}>
          {result.flood_detected ? 'Flood detected' : 'No flood detected'} ({(p * 100).toFixed(0)}%)
        </strong>
        <span className="status-pill" style={{ fontSize: '10px' }}>{result.data_label || 'PREDICTED'}</span>
      </div>
      {result.overlay_png_base64 && !compact && (
        <img
          src={`data:image/png;base64,${result.overlay_png_base64}`}
          alt="Water (blue), people (red), vehicles (yellow), boats (green)"
          style={{ width: '100%', borderRadius: '4px', marginBottom: '6px' }}
        />
      )}
      {result.closest_description && row('Closest description', result.closest_description)}
      {row('Water coverage', `${result.water_coverage_pct ?? 0}%`)}
      {row('People (in water)', `${result.people_detected ?? 0} (${result.people_in_water ?? 0})`)}
      {row('Vehicles (in water)', `${result.vehicles_detected ?? 0} (${result.vehicles_in_water ?? 0})`)}
      {row('Boats', result.boats_detected ?? 0)}
      {row('Suggested severity', (
        <span style={{ color: sevColour[result.suggested_severity || 'LOW'] }}>{result.suggested_severity}</span>
      ))}
      {result.inference_ms !== undefined && row('Inference time', `${result.inference_ms} ms`)}
      {!compact && (
        <div className="text-muted" style={{ fontSize: '11px', marginTop: '6px', lineHeight: 1.4 }}>
          Water depth is not estimated from photos. Muddy water can be under-counted in the coverage figure.
          The operator confirms severity when verifying the incident.
        </div>
      )}
    </div>
  );
};
