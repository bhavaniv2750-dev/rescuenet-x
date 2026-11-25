import { describe, expect, it } from 'vitest';
import { BASEMAPS } from './basemaps';
import { PRESETS, PRESET_ORDER } from './presets';
import { kindOfFacility, presetIcon } from './styleMarkers';
import { esc, facilityStyle, incidentIcon, popup, sevColor } from './markers';

describe('basemaps', () => {
  it('offers dark, light, voyager and standard maps, with attribution and no API key in any URL', () => {
    expect(Object.keys(BASEMAPS).sort()).toEqual(['dark', 'light', 'standard', 'voyager']);
    for (const b of Object.values(BASEMAPS)) {
      expect(b.attribution).toMatch(/OpenStreetMap/);
      expect(b.url).not.toMatch(/key=|apikey|token|access_token/i);
    }
    expect(BASEMAPS.dark.attribution).toMatch(/CARTO/);
  });
});

describe('markers and popups', () => {
  it('escapes every backend value placed in a popup', () => {
    const html = popup('<img src=x onerror=alert(1)>', 'HIGH', [['Message', '<script>x</script>'], ['Empty', '']]);
    expect(html).not.toMatch(/<img|<script/);
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('Empty');          // empty fields are not shown, nothing is invented
  });
  it('esc handles quotes and null', () => { expect(esc(`a"b'c&`)).toBe('a&quot;b&#39;c&amp;'); expect(esc(null)).toBe(''); });
  it('incident markers differ by severity in colour AND glyph', () => {
    const glyphs = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW'].map((s) => (incidentIcon(s).options.html as string).match(/>([^<]+)<\/span>/)?.[1]);
    expect(new Set(glyphs).size).toBe(4);
    expect(new Set(['CRITICAL', 'HIGH', 'MODERATE', 'LOW'].map(sevColor)).size).toBe(4);
  });
  it('facility types have distinct letters', () => {
    const g = ['HOSPITAL', 'SHELTER', 'RELIEF_CAMP', 'RESCUE_HQ', 'POLICE_STATION', 'FIRE_STATION', 'SCHOOL'].map((t) => facilityStyle(t).g);
    expect(new Set(g).size).toBe(7);
  });
});

describe('visual presets', () => {
  it('has the four presets, classic first', () => { expect(PRESET_ORDER).toEqual(['classic', 'tactical', 'navigation', 'flood']); expect(Object.keys(PRESETS)).toHaveLength(4); });
  it('every preset draws every kind with a text label and a distinct shape per category', () => {
    for (const p of PRESET_ORDER) for (const k of ['incident', 'team', 'hospital', 'shelter', 'camp', 'gauge'] as const) expect(String(presetIcon(p, k, { severity: 'HIGH', facilityType: 'HOSPITAL' }).options.html).length).toBeGreaterThan(20);
    const shapes = (['team', 'hospital', 'shelter', 'camp', 'gauge'] as const).map((k) => String(presetIcon('flood', k).options.html).match(/<(polygon|rect|path|circle)/)?.[0] + String(presetIcon('flood', k).options.html).match(/points="[^"]+"|d="M16[^"]{0,12}/)?.[0]);
    expect(new Set(shapes).size).toBe(5);
  });
  it('critical incidents get alert rings in tactical and flood only', () => {
    expect(String(presetIcon('tactical', 'incident', { severity: 'CRITICAL' }).options.html)).toContain('rn-ring');
    expect(String(presetIcon('flood', 'incident', { severity: 'CRITICAL' }).options.html)).toContain('rn-ring');
    expect(String(presetIcon('navigation', 'incident', { severity: 'CRITICAL' }).options.html)).not.toContain('rn-ring');
    expect(String(presetIcon('tactical', 'incident', { severity: 'HIGH' }).options.html)).not.toContain('rn-ring');
  });
  it('selected markers are marked', () => { expect(String(presetIcon('tactical', 'incident', { severity: 'LOW', selected: true }).options.html)).toContain('is-sel'); });
  it('facility types map to categories', () => { expect(kindOfFacility('HOSPITAL')).toBe('hospital'); expect(kindOfFacility('SHELTER')).toBe('shelter'); expect(kindOfFacility('RELIEF_CAMP')).toBe('camp'); expect(kindOfFacility('FIRE_STATION')).toBe('facility'); });
});
