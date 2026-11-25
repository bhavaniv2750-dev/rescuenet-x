/** Basemap providers. No API key and no paid service is involved.
 *  CARTO Dark Matter / Positron: free for non-commercial use with attribution (https://carto.com/basemaps, https://carto.com/attributions); data (c) OpenStreetMap contributors (ODbL).
 *  OpenStreetMap standard tiles: https://operations.osmfoundation.org/policies/tiles/ (light use, attribution required, no bulk download).
 *  Attribution strings must stay visible; they are shown by the map's attribution control. */
export type BasemapId = 'dark' | 'light' | 'voyager' | 'standard';
export interface Basemap { id: BasemapId; label: string; url: string; attribution: string; subdomains?: string; maxZoom: number; background: string }

const OSM = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors';
const CARTO = '&copy; <a href="https://carto.com/attributions" target="_blank" rel="noreferrer">CARTO</a>';

export const BASEMAPS: Record<BasemapId, Basemap> = {
  dark: { id: 'dark', label: 'Dark', url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', attribution: `${OSM} ${CARTO}`, subdomains: 'abcd', maxZoom: 20, background: '#0d1626' },
  light: { id: 'light', label: 'Light', url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', attribution: `${OSM} ${CARTO}`, subdomains: 'abcd', maxZoom: 20, background: '#e9edf2' },
  voyager: { id: 'voyager', label: 'Voyager', url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', attribution: `${OSM} ${CARTO}`, subdomains: 'abcd', maxZoom: 20, background: '#e8e4dc' },
  standard: { id: 'standard', label: 'Streets', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', attribution: OSM, maxZoom: 19, background: '#e6e2d8' },
};
export const BASEMAP_KEY = 'rescuenet.basemap';
export const STYLE_KEY = 'rescuenet.mapstyle';
