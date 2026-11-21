# Project Tasks and Phases

This roadmap distinguishes the current starter from planned work. Mark a task complete only after it is implemented and verified in the repository.

## Phase 1 — Project setup and baseline

- [x] Establish React + TypeScript + Vite frontend scaffold.
- [x] Establish FastAPI backend scaffold and requirements file.
- [x] Add starter operations console and map view.
- [x] Add initial API routes for dashboard, forecasts, incidents, alert simulation, missions, facilities, supervisor tasks, and image intake.
- [x] Add local SQLite persistence for prototype records.
- [x] Add README and `.gitignore` excluding `.env` and local runtime artifacts.
- [ ] Run clean Python environment install and confirm backend starts from a fresh clone.
- [ ] Run `npm install`, `npm run dev`, and `npm run build` from a fresh clone; resolve dependency/build issues.
- [ ] Add `.env.example` only if environment variables become necessary; use placeholders only.
- [ ] Add basic automated test commands and CI workflow.

**Exit criteria:** a fresh checkout starts locally from documented steps; no secrets or runtime data are tracked.

## Phase 2 — Authentication, authorization, and audit foundations

- [ ] Define roles: administrator, supervisor, coordinator, responder, verified volunteer, read-only analyst.
- [ ] Choose an authentication approach appropriate to deployment; document session/token lifecycle.
- [ ] Add login/logout and protected routes/API endpoints.
- [ ] Implement server-side role and permission checks (not frontend-only gating).
- [ ] Add audit events for sign-in, permission changes, alert actions, mission assignments, and incident state changes.
- [ ] Add rate limiting, secure CORS configuration, request validation, and safe error responses.
- [ ] Test unauthorized, forbidden, expired-session, and privilege-escalation cases.

**Exit criteria:** protected workflows are inaccessible without the appropriate role; audit events can be reviewed. Do not use real personal/responder data before this phase is complete.

## Phase 3 — Incident and rescue record manager

- [ ] Finalize incident schema: ID, coordinates, category, severity, report time, source, verification status, needs, attachments, owner, and timeline.
- [ ] Add create/read/update/filter workflows and validation for incidents.
- [ ] Add detailed rescue mission records: incident link, team, assignment/acceptance/start/arrival/completion times, status, resource needs, notes, outcome, and escalation reason.
- [ ] Add lifecycle/state-transition rules and audit trail.
- [ ] Add duplicate-report detection assistance without automatically discarding reports.
- [ ] Add pagination, search, empty/loading/error states, and API tests.

**Exit criteria:** incidents and missions have stable IDs, validated state transitions, and traceable histories.

## Phase 4 — Digital-twin map and flood-risk visualization

- [ ] Standardize coordinate reference and validation (WGS84 latitude/longitude for web map inputs).
- [ ] Show incident layers, facilities, flood-risk zones/overlays, and responder assets only when source/status is known.
- [ ] Add layer controls, legend, filters, marker clustering, and map/list selection synchronization.
- [ ] Add source, timestamp, freshness, and simulated/real labels to map layers.
- [ ] Add graceful handling for tile/API/network failures.
- [ ] Test responsive layouts and keyboard-accessible non-map alternatives.

**Exit criteria:** users can identify what each layer represents, when it was updated, and whether it is simulated.

## Phase 5 — Forecasting service (30–60 minute target)

- [ ] Define target variable(s), geography, units, horizon, and minimum input freshness.
- [ ] Create data-ingestion adapters for approved rainfall, water-level, weather, terrain, and historical sources.
- [ ] Track missing values, sensor quality, timestamps, geographic coverage, and source provenance.
- [ ] Establish naive baselines before selecting a model (e.g. persistence/threshold baselines where appropriate).
- [ ] Train and validate candidate models using time-aware splits and geographically meaningful holdouts.
- [ ] Measure appropriate regression/classification metrics and calibrate uncertainty; document limitations.
- [ ] Return horizon, estimate, uncertainty, model/version, input timestamps, and stale/unavailable flags from the API.
- [ ] Add model/data monitoring and safe fallback behavior.
- [ ] Keep prototype/simulated forecast clearly labelled until validated.

**Exit criteria:** forecast output is reproducible, evaluated against baselines, and never hides stale or missing inputs.

## Phase 6 — Geo-targeted alert workflows

- [ ] Define alert schema: target geometry, severity, message, source, created/expiry time, approver, channel, and delivery state.
- [ ] Add target-area selection and audience preview.
- [ ] Add approval and confirmation steps for consequential alerts.
- [ ] Keep simulation mode visually distinct from real delivery.
- [ ] Integrate authorized delivery channels only after access approval, legal review, and delivery/failure testing.
- [ ] Record per-channel delivery receipts and failures where providers support them.
- [ ] Add expiry, cancellation, duplicate suppression, and audit history.

**Exit criteria:** UI status truthfully reflects whether an alert was drafted, simulated, queued, delivered, or failed. No false claims of universal delivery.

## Phase 7 — Rescue team and verified volunteer coordination

- [ ] Define responder/volunteer profile, verification status, skills, service area, availability, and consent.
- [ ] Build verification review and expiry/revalidation flow.
- [ ] Match candidate teams by proximity, skills, availability, and task requirements; expose reasons and limitations.
- [ ] Keep unverified users out of dispatch-ready pools.
- [ ] Add supervisor approval, assignment acknowledgement, reassignment, and escalation flows.
- [ ] Protect contact details and precise locations with role-based access and retention rules.

**Exit criteria:** assignment suggestions are explainable, verified status is explicit, and a human authorizes dispatch.

## Phase 8 — Supervisor agent and operations queue

- [ ] Define permitted inputs, outputs, tools, and safety boundaries for the supervisor agent.
- [ ] Summarize reports and flag missing/conflicting details with source links.
- [ ] Rank suggested tasks using documented criteria; display the rationale and data limitations.
- [ ] Require human approval for alert escalation, mission assignment, and incident closure.
- [ ] Add prompt-injection/untrusted-input handling for submitted reports and uploaded content.
- [ ] Log agent version, input references, recommendation, reviewer, and final decision.
- [ ] Evaluate recommendation quality and failure cases with a reviewed test set.

**Exit criteria:** agent output is advisory, explainable, auditable, and cannot independently execute high-impact actions.

## Phase 9 — Nearby facilities and route context

- [ ] Define facility categories and required fields (location, source, last verified, capacity/status if known).
- [ ] Add proximity search and distance calculation.
- [ ] Integrate trusted facility datasets with attribution and update cadence.
- [ ] Show unknown/stale capacity explicitly; never infer that a facility is open.
- [ ] Add accessibility, operating status, and contact fields only when sourced and verified.
- [ ] Test boundary cases, missing coordinates, duplicate records, and stale facility data.

**Exit criteria:** facility search provides provenance and does not overstate availability or safety.

## Phase 10 — Flood-level observations and computer vision

- [ ] Define water-level observation schema, units, location, time, sensor/source, quality, and verification status.
- [ ] Set upload size/type limits and validate file content server-side.
- [ ] Define consent, retention, access, and deletion rules for submitted images.
- [ ] Curate licensed, representative labelled images; record class definitions and geographic/weather coverage.
- [ ] Establish baseline and held-out evaluation before selecting a CV model.
- [ ] Return analysis status, model/version, confidence/uncertainty, and failure warnings.
- [ ] Add human verification/correction and audit trail.

**Exit criteria:** placeholder detector is clearly labelled until a real model is evaluated; image output is not treated as ground truth.

## Phase 11 — Real-data integrations and data quality

- [ ] Verify API access, credentials, terms, attribution, quotas, and intended use for each public source.
- [ ] Build isolated connectors with retries, timeouts, rate-limit handling, and observability.
- [ ] Normalize units, timestamps, coordinates, and missing-data representations.
- [ ] Store provenance and ingestion history; flag stale feeds.
- [ ] Separate development/demo datasets from production-connected datasets.
- [ ] Add contract tests using fixtures and controlled mock responses.

**Exit criteria:** each integration has documented provenance, failure behavior, and freshness expectations.

## Phase 12 — Testing, deployment, and readiness review

- [ ] Add backend unit/API tests and frontend component/integration tests.
- [ ] Add end-to-end smoke tests for incident → task → mission → outcome and alert simulation.
- [ ] Run dependency/security scans and secret scanning.
- [ ] Add structured logs, metrics, health/readiness checks, backups, and restore test.
- [ ] Add deployment configuration, HTTPS, database migrations, least-privilege credentials, and CORS allowlist.
- [ ] Conduct privacy, accessibility, threat, model-risk, and operational safety reviews.
- [ ] Document rollback, outage mode, escalation contacts, and limitations.
- [ ] Obtain relevant authority/organization approval before any real operational use.

**Exit criteria:** reproducible deployment and test evidence exist; no production claims are made before approval.

## Cross-phase priority order

1. Reproducible setup and baseline tests.
2. Record schemas and API contracts.
3. Authentication/authorization before sensitive multi-user workflows.
4. Incident and mission auditability.
5. Map/data provenance and stale-data handling.
6. Forecast evaluation and real-data adapters.
7. Alert simulation and approval safeguards.
8. Verified volunteer and supervisor workflows.
9. Facilities, image analysis, operational hardening.
