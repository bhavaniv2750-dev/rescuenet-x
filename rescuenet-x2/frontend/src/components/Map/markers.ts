import L from 'leaflet';
import { SEVERITY_COLOR } from '../../design/tokens';

export const esc = (v: unknown): string => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string));

const SEV_GLYPH: Record<string, string> = { CRITICAL: '!!', HIGH: '!', MODERATE: '▲', LOW: '●' };
export const sevColor = (s: string) => SEVERITY_COLOR[(s || '').toUpperCase() as keyof typeof SEVERITY_COLOR] ?? '#93a4bd';

/** Marker shapes differ by kind (circle incident, rounded square squad, square facility, diamond gauge) and incident glyphs differ by
 *  severity, so meaning never depends on colour alone. Every marker has a text title for assistive technology. */
export function incidentIcon(severity: string): L.DivIcon {
  const c = sevColor(severity), g = SEV_GLYPH[(severity || '').toUpperCase()] ?? '?';
  return L.divIcon({ className: 'rn-pin', html: `<span class="rn-pin-body rn-pin-incident" style="--c:${c}" aria-hidden="true">${g}</span>`, iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -14] });
}
export function teamIcon(available: boolean): L.DivIcon {
  return L.divIcon({ className: 'rn-pin', html: `<span class="rn-pin-body rn-pin-team" style="--c:${available ? '#6cb6ff' : '#b69cff'}" aria-hidden="true">✚</span>`, iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -13] });
}
const FAC: Record<string, { g: string; c: string }> = {
  HOSPITAL: { g: 'H', c: '#f59ac8' }, SHELTER: { g: 'S', c: '#34d399' }, RELIEF_CAMP: { g: 'R', c: '#34d399' }, RESCUE_HQ: { g: 'Q', c: '#7dd3fc' },
  POLICE_STATION: { g: 'P', c: '#a5b4fc' }, FIRE_STATION: { g: 'F', c: '#ffb86b' }, SCHOOL: { g: 'E', c: '#34d399' },
};
export const facilityStyle = (t: string) => FAC[t] ?? { g: 'F', c: '#93a4bd' };
export function facilityIcon(type: string): L.DivIcon {
  const f = facilityStyle(type);
  return L.divIcon({ className: 'rn-pin', html: `<span class="rn-pin-body rn-pin-facility" style="--c:${f.c}" aria-hidden="true">${f.g}</span>`, iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -12] });
}
export function gaugeIcon(): L.DivIcon {
  return L.divIcon({ className: 'rn-pin', html: '<span class="rn-pin-body rn-pin-gauge" style="--c:#7dd3fc" aria-hidden="true"><i></i></span>', iconSize: [20, 20], iconAnchor: [10, 10], popupAnchor: [0, -11] });
}
export function clusterIcon(cluster: { getChildCount(): number }): L.DivIcon {
  const n = cluster.getChildCount();
  return L.divIcon({ className: 'rn-cluster-wrap', html: `<span class="rn-cluster" aria-label="${n} markers">${n}</span>`, iconSize: [36, 36] });
}

/** Popup markup from real backend fields only; every value is escaped. */
export function popup(title: string, badge: string | null, rows: [string, unknown][]): string {
  const body = rows.filter(([, v]) => v !== null && v !== undefined && v !== '').map(([k, v]) => `<div class="rn-pop-row"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('');
  return `<div class="rn-pop"><div class="rn-pop-head"><strong>${esc(title)}</strong>${badge ? `<span class="rn-pop-badge">${esc(badge)}</span>` : ''}</div><dl>${body}</dl></div>`;
}
