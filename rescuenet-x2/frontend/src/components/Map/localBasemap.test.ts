import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { searchLocal, paletteFor, type LocalData } from './localBasemap'

const dir = join(__dirname, '../../../public/basemap')
const rd = (n: string) => JSON.parse(readFileSync(join(dir, n), 'utf8'))
const data = (): LocalData => ({
  wards: rd('wards.json'), roads: rd('roads.json'), rail: rd('rail.json'), rivers: rd('rivers.json'), lakes: rd('lakes.json'),
  places: rd('places.json'), airports: rd('airports.json'), urban: rd('urban.json'), states: rd('states.json'), manifest: rd('manifest.json'), osm: {},
})

describe('bundled local basemap', () => {
  it('ships real ward polygons inside the Bengaluru window with a documented licence', () => {
    const d = data()
    expect(d.wards.features.length).toBeGreaterThan(200)
    expect(d.manifest.sources.length).toBeGreaterThan(0)
    expect(JSON.stringify(d.manifest)).toMatch(/CC BY-SA|public domain/i)
    const ring = (d.wards.features[0].geometry as any).coordinates.flat(2)
    expect(ring[0]).toBeGreaterThan(77); expect(ring[0]).toBeLessThan(78)
  })
  it('does not claim OSM street data it does not contain', () => {
    expect(data().manifest.osm_layers_present).toBe(false)
  })
  it('search finds wards by prefix and returns plausible coordinates', () => {
    const h = searchLocal(data(), 'koramangala')
    expect(h.length).toBeGreaterThan(0)
    expect(h[0].lat).toBeGreaterThan(12.8); expect(h[0].lat).toBeLessThan(13.1)
    expect(searchLocal(data(), 'zzzzqq')).toEqual([])
  })
  it('has distinct dark and light palettes', () => {
    expect(paletteFor('dark', 'classic').land).not.toBe(paletteFor('light', 'classic').land)
  })
})
