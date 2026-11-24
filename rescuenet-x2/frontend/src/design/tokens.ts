/** Mirrors design/tokens.css for code that needs the values (map colours, media queries). */
export const BREAKPOINTS = { sm: 480, md: 768, lg: 1024, xl: 1440 } as const;
export const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW'] as const;
export type Severity = (typeof SEVERITY_ORDER)[number];
export const SEVERITY_COLOR: Record<Severity, string> = { CRITICAL: '#ff6b6b', HIGH: '#ff9f43', MODERATE: '#f7d046', LOW: '#6cb6ff' };
/** Provenance labels. LIVE is allowed only where the data source genuinely supports it. */
export const PROVENANCE = ['SIMULATED', 'HISTORICAL', 'OBSERVED', 'LIVE', 'STALE', 'UNAVAILABLE'] as const;
export type Provenance = (typeof PROVENANCE)[number];
