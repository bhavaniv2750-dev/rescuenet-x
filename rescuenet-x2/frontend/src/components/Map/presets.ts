import type { BasemapId } from './basemaps';

export type PresetId = 'classic' | 'tactical' | 'navigation' | 'flood';
export interface Preset { id: PresetId; label: string; blurb: string; basemap: BasemapId; cards: boolean; search: boolean; labels: boolean; rings: boolean }

/** Four visual presets over the SAME coordinates, records and overlays. Only the presentation differs. */
export const PRESETS: Record<PresetId, Preset> = {
  classic: { id: 'classic', label: 'Classic', blurb: 'The current look: compact square and round pins, dark basemap in the console.', basemap: 'dark', cards: false, search: false, labels: false, rings: false },
  tactical: { id: 'tactical', label: 'Tactical', blurb: 'Dispatch-room look: muted dark urban basemap, teardrop markers, glow, alert rings, floating labels.', basemap: 'dark', cards: false, search: false, labels: true, rings: true },
  navigation: { id: 'navigation', label: 'Navigation', blurb: 'Familiar street-map look: Voyager road map, location pins, search, information card.', basemap: 'voyager', cards: true, search: true, labels: false, rings: false },
  flood: { id: 'flood', label: 'Flood Intelligence', blurb: 'Detailed street map toned down, with category-shaped emergency markers, catchments and alert areas.', basemap: 'voyager', cards: true, search: true, labels: true, rings: true },
};
export const PRESET_ORDER: PresetId[] = ['classic', 'tactical', 'navigation', 'flood'];
