import L from 'leaflet';
import type { PresetId } from './presets';
import { facilityIcon, gaugeIcon, incidentIcon, sevColor, teamIcon } from './markers';

export type MarkerKind = 'incident' | 'team' | 'hospital' | 'shelter' | 'camp' | 'facility' | 'gauge';
export interface IconOpts { severity?: string; available?: boolean; facilityType?: string; selected?: boolean }

const GLYPH: Record<string, string> = { CRITICAL: '!!', HIGH: '!', MODERATE: '▲', LOW: '●' };
// 24x24 icon paths (simple geometric shapes drawn for this project)
const P = {
  cross: 'M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z',
  house: 'M12 3l9 8h-3v9h-5v-6h-2v6H6v-9H3z',
  tent: 'M12 3l10 17H2zM12 10l3.5 10h-7z',
  shield: 'M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5z',
  drop: 'M12 2s7 7.5 7 12a7 7 0 01-14 0c0-4.5 7-12 7-12z',
};
const DROP = 'M15 39C15 39 2 24 2 14a13 13 0 0126 0c0 10-13 25-13 25z';
const HEX = '16,2 28,9 28,23 16,30 4,23 4,9';

const FAC_LETTER: Record<string, string> = { RESCUE_HQ: 'Q', POLICE_STATION: 'P', FIRE_STATION: 'F', SCHOOL: 'E' };
export function kindOfFacility(t: string): MarkerKind { return t === 'HOSPITAL' ? 'hospital' : t === 'SHELTER' || t === 'SCHOOL' ? 'shelter' : t === 'RELIEF_CAMP' ? 'camp' : 'facility'; }
const COLOR: Record<string, string> = { team: '#22b8cf', hospital: '#ff7aa8', shelter: '#34d399', camp: '#5eead4', facility: '#a5b4fc', gauge: '#22d3ee' };
const colorOf = (k: MarkerKind, o: IconOpts) => (k === 'incident' ? sevColor(o.severity || '') : k === 'team' && o.available === false ? '#b69cff' : COLOR[k]);
const label = (k: MarkerKind, o: IconOpts) => (k === 'incident' ? `${o.severity} incident` : k === 'team' ? 'Rescue squad' : k === 'gauge' ? 'River gauge' : (o.facilityType || k).replace(/_/g, ' ').toLowerCase());

function glyphSvg(k: MarkerKind, o: IconOpts, fill: string, cx: number, cy: number, size: number): string {
  const sc = size / 24, tr = `translate(${cx - size / 2} ${cy - size / 2}) scale(${sc})`;
  if (k === 'incident') return `<text x="${cx}" y="${cy + size * 0.36}" text-anchor="middle" font-size="${size * 0.95}" font-weight="800" font-family="Inter,sans-serif" fill="${fill}">${GLYPH[(o.severity || '').toUpperCase()] ?? '?'}</text>`;
  const path = k === 'hospital' ? P.cross : k === 'shelter' ? P.house : k === 'camp' ? P.tent : k === 'team' ? P.shield : k === 'gauge' ? P.drop : '';
  if (path) return `<path transform="${tr}" d="${path}" fill="${fill}"/>`;
  return `<text x="${cx}" y="${cy + size * 0.36}" text-anchor="middle" font-size="${size * 0.9}" font-weight="800" font-family="Inter,sans-serif" fill="${fill}">${FAC_LETTER[o.facilityType || ''] ?? 'F'}</text>`;
}

/** Marker for a preset. Meaning never rests on colour alone: shape, icon and (for incidents) a severity glyph differ, and every marker carries a title. */
export function presetIcon(preset: PresetId, kind: MarkerKind, o: IconOpts = {}): L.DivIcon {
  if (preset === 'classic') {
    return kind === 'incident' ? incidentIcon(o.severity || '') : kind === 'team' ? teamIcon(o.available !== false) : kind === 'gauge' ? gaugeIcon() : facilityIcon(o.facilityType || 'SHELTER');
  }
  const c = colorOf(kind, o), crit = kind === 'incident' && (o.severity || '').toUpperCase() === 'CRITICAL';
  const sel = o.selected ? ' is-sel' : '';
  const rings = crit && preset !== 'navigation' ? '<span class="rn-ring"></span><span class="rn-ring r2"></span>' : '';
  const aria = `role="img" aria-label="${label(kind, o)}"`;
  if (preset === 'navigation' || (preset === 'tactical' && kind !== 'gauge')) {
    const tact = preset === 'tactical';
    const body = tact
      ? `<path d="${DROP}" fill="#0b1220" stroke="${c}" stroke-width="2.4"/><circle cx="15" cy="14" r="9" fill="${c}" fill-opacity=".16"/>${glyphSvg(kind, o, c, 15, 14, 13)}`
      : `<path d="${DROP}" fill="${c}" stroke="#fff" stroke-width="1.6"/><circle cx="15" cy="14" r="8.2" fill="#fff"/>${glyphSvg(kind, o, c, 15, 14, 12.5)}`;
    return L.divIcon({ className: 'rn-m-wrap', html: `<span class="rn-m rn-m-drop ${tact ? 'tact' : 'nav'}${sel}" style="--c:${c}">${rings}<svg ${aria} viewBox="0 0 30 40" width="30" height="40">${body}</svg></span>`, iconSize: [30, 40], iconAnchor: [15, 39], popupAnchor: [0, -36], tooltipAnchor: [14, -26] });
  }
  // flood intelligence (and tactical gauges): category-shaped badges
  let shape: string;
  if (kind === 'incident') shape = `<circle cx="16" cy="16" r="13" fill="${c}" stroke="#fff" stroke-width="2"/>`;
  else if (kind === 'team') shape = `<polygon points="${HEX}" fill="#0b1220" stroke="${c}" stroke-width="2.4"/>`;
  else if (kind === 'hospital') shape = `<rect x="3" y="3" width="26" height="26" rx="6" fill="#fff" stroke="${c}" stroke-width="2.6"/>`;
  else if (kind === 'shelter') shape = `<path d="M16 2L29 12v16H3V12z" fill="#0b1220" stroke="${c}" stroke-width="2.4"/>`;
  else if (kind === 'camp') shape = `<path d="M16 3L30 28H2z" fill="#0b1220" stroke="${c}" stroke-width="2.4" stroke-linejoin="round"/>`;
  else if (kind === 'gauge') shape = `<polygon points="16,2 30,16 16,30 2,16" fill="#0b1220" stroke="${c}" stroke-width="2.4"/>`;
  else shape = `<rect x="4" y="4" width="24" height="24" rx="3" fill="#0b1220" stroke="${c}" stroke-width="2.4"/>`;
  const inner = kind === 'incident' ? '#0a101c' : kind === 'hospital' ? c : c;
  const cy = kind === 'camp' ? 21 : kind === 'shelter' ? 19 : 16;
  return L.divIcon({ className: 'rn-m-wrap', html: `<span class="rn-m rn-m-badge flood${sel}" style="--c:${c}">${rings}<svg ${aria} viewBox="0 0 32 32" width="32" height="32">${shape}${glyphSvg(kind, o, inner, 16, cy, kind === 'incident' ? 14 : 15)}</svg></span>`, iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -18], tooltipAnchor: [16, -4] });
}

/** Legend swatch drawn with the very same marker markup. */
export function legendSvg(preset: PresetId, kind: MarkerKind, o: IconOpts = {}): string {
  return String(presetIcon(preset, kind, o).options.html ?? '');
}
