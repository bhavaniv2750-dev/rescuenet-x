# Design System

**Product mood:** calm, operational, high-contrast, map-first. The interface should feel like a dependable emergency operations console, not a game or a flashy AI demo.

## 1. Design principles

- **Clarity under pressure:** prioritize incident severity, location, status, and next action.
- **Map-first, not map-only:** pair geographic visualization with readable lists, counts, and accessible text alternatives.
- **Trust through provenance:** show source, last updated time, and real/simulated/derived status near important data.
- **Uncertainty is visible:** forecasts include horizon, uncertainty, freshness, and a plain-language caveat.
- **Color is not the only signal:** combine color with labels, icons, and patterns.
- **Progressive disclosure:** keep the main dashboard focused; place detailed rescue/audit records in drill-down panels.
- **Human-centered control:** high-impact actions need confirmation, clear consequences, and an approval state.
- **Responsive and accessible:** support laptop/tablet layouts, keyboard operation, visible focus, and sufficient contrast.

## 2. Color palette

Use these as design tokens; validate contrast for final text/background combinations.

| Token | Hex | Intended use |
|---|---|---|
| `--color-ink` | `#102A43` | Main text / deep navigation |
| `--color-navy` | `#12304A` | Header, navigation, high-contrast surfaces |
| `--color-blue` | `#1677C8` | Primary actions, links, selected map tools |
| `--color-cyan` | `#22B8CF` | Secondary data accents, water-related visuals |
| `--color-bg` | `#F4F7FA` | Application background |
| `--color-surface` | `#FFFFFF` | Cards, panels, dialogs |
| `--color-border` | `#D7E0E8` | Dividers, input borders |
| `--color-muted` | `#526579` | Secondary text (check contrast by use) |
| `--color-success` | `#237A57` | Verified/complete states with text label |
| `--color-warning` | `#A85D00` | Warning/pending review |
| `--color-danger` | `#B42332` | Critical severity / destructive action |
| `--color-neutral` | `#64748B` | Unknown/inactive states |

### Risk and status mapping

- **Critical:** danger red + `Critical` label + distinct icon.
- **High:** dark orange/red variant + `High` label.
- **Moderate:** amber + `Moderate` label.
- **Low:** blue/teal + `Low` label.
- **Unknown/stale:** neutral gray + explicit `Unknown` or `Data stale` label.
- **Simulated data:** neutral badge such as `SIMULATED`; never rely on color alone.

Do not use green to imply a location is safe unless an authoritative, current assessment supports that conclusion.

## 3. Typography

- **Font stack:** `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.
- **Page title:** 24–30 px, semibold.
- **Section title:** 16–20 px, semibold.
- **Body:** 14–16 px, regular.
- **Metadata / timestamps:** 12–13 px; maintain readable contrast.
- **Numeric KPIs:** 24–32 px, semibold; pair every number with a clear label and time context.
- Use tabular numerals for metrics when available. Avoid long all-caps labels except compact status badges.

## 4. Spacing, shape, and layout

- Base spacing scale: 4, 8, 12, 16, 24, 32 px.
- Card radius: 10–14 px; input/button radius: 8–10 px.
- Use subtle borders and restrained shadows; avoid excessive glassmorphism or gradients that reduce legibility.
- Keep primary actions consistent and visually distinct from destructive actions.
- Dashboard desktop layout: persistent navigation, compact top status area, main map/workspace, contextual incident/task panels.
- Mobile/tablet: stack panels; map controls must not cover critical markers or actions.

## 5. UI component inventory

- **Navigation:** active page, keyboard focus, clear labels.
- **KPI card:** metric, label, time/source context, optional trend with explanation.
- **Map legend:** risk category, incident type, asset type, and simulated-data indicator.
- **Incident marker:** severity, type, verification status; cluster overlapping points.
- **Status badge:** `New`, `Needs verification`, `Verified`, `Assigned`, `In progress`, `Resolved`, `Simulated`, `Stale`.
- **Alert composer:** target area, message, severity, expiry, preview, simulation/live-mode disclosure, confirmation.
- **Forecast panel:** 30/45/60-minute horizon selector, estimate, uncertainty, source freshness, coverage and caveat.
- **Incident/rescue detail panel:** timeline, assigned team, needs, notes, evidence, outcome and audit history.
- **Facility result row:** type, distance, source, last verified time, known capacity/availability only when confirmed.
- **Task queue:** priority, reason, source records, owner, due/age, approve/reject/escalate controls.
- **Upload/evidence component:** file constraints, consent notice where applicable, upload progress, processing status, result caveat.
- **Feedback states:** loading skeleton, empty state, inline error, retry, stale-data warning, confirmation dialog.

## 6. Interaction and accessibility rules

- Confirm before sending an alert simulation, assigning a mission, or performing destructive changes.
- Never use a disabled control without explaining why when the reason is not obvious.
- Provide keyboard-operable controls, semantic headings, accessible labels, and visible focus rings.
- Use non-color cues for severity and status; avoid flashing or rapidly pulsing alerts.
- Make timestamps and units explicit (for example, `Updated 14:05 IST`, `water level: metres`).
- Keep alert language concise and distinguish confirmed facts from reported/unverified information.

## 7. Example design tokens

```css
:root {
  --color-ink: #102A43;
  --color-navy: #12304A;
  --color-blue: #1677C8;
  --color-cyan: #22B8CF;
  --color-bg: #F4F7FA;
  --color-surface: #FFFFFF;
  --color-border: #D7E0E8;
  --color-muted: #526579;
  --color-success: #237A57;
  --color-warning: #A85D00;
  --color-danger: #B42332;
  --radius-card: 12px;
  --radius-control: 8px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
}
```
