# Product Requirements Document (PRD)

**Product:** Flood Digital Twin + RescueNet X 2.0  
**Version:** 0.1 — prototype baseline  
**Region:** Bengaluru and nearby flood-prone areas, Karnataka, India  
**Product principle:** Predict → Visualize → Respond

## 1. Product overview

RescueNet X is a disaster-intelligence and emergency-response coordination prototype that combines geographic flood-risk visualization, short-horizon risk estimates, incident reporting, alert workflows, rescue mission records, nearby facility discovery, and supervisory oversight in one interface. A digital-twin-style map gives operators a shared geographic picture while records and tasks support coordinated response.

The system uses a hybrid data strategy. Real public datasets may be integrated where access and terms permit; all simulated, synthetic, stale, or derived values must be labelled. It is a decision-support prototype, not an official warning authority or replacement for emergency services.

## 2. Problem statement

During urban flooding, information about rainfall, water levels, affected locations, vulnerable residents, passable routes, shelters, and available responders can be fragmented or delayed. Poor connectivity and inconsistent reporting make it difficult to form a timely shared picture, prioritize incidents, and keep track of rescue outcomes. Existing disconnected tools can also make it hard to distinguish confirmed reports from unverified claims.

## 3. Goals and success criteria

### Product goals

1. Give operators a geographic overview of reported incidents and flood-risk estimates.
2. Surface 30-, 45-, and 60-minute prototype forecast horizons with visible uncertainty and data freshness.
3. Support structured incident intake and geo-targeted alert drafting/simulation.
4. Maintain traceable rescue mission, responder/volunteer verification, and outcome records.
5. Help supervisors review queues, prioritize work, and approve consequential actions.
6. Find nearby relevant facilities using location and facility type.
7. Accept flood-level/image evidence for future model-assisted analysis while retaining human review.

### MVP acceptance criteria

- Frontend and backend can be started locally using documented commands.
- Dashboard and map clearly distinguish simulated from connected real data.
- Forecast endpoint returns horizon, estimate/risk category, uncertainty/confidence information, timestamp/freshness, and caveat; no unsupported accuracy claims.
- Incident, simulated alert, mission, and supervisor-task records can be created/read where supported by the current API.
- Facility search returns results with distance/location metadata when available and labels demo results.
- Image intake reports upload/analysis status without representing placeholder output as a trained detector.
- Secret files and local runtime artifacts are excluded from Git.
- Automated tests cover core API contracts and critical state transitions before release.

## 4. Target users

- **Emergency operations coordinators:** monitor incident load, risk areas, and response status.
- **Field rescue teams:** receive assigned tasks and record status/outcomes (future authenticated workflow).
- **Verified volunteers:** offer assistance within verified skills, location, and availability (future workflow).
- **Supervisors / district administrators:** review priorities, approve high-impact actions, and audit decisions.
- **Community reporters:** submit location-tagged observations through a safe, limited reporting interface (future workflow).
- **Analysts / researchers:** evaluate forecast performance and data quality using approved, privacy-safe datasets.

## 5. Core MVP features

### A. Operations dashboard and digital-twin map
- Show incident markers, risk overlays/summary metrics, response assets, and facility locations.
- Provide map navigation and clear legends, timestamps, and source labels.
- Allow filters by incident status, severity, and data type where supported.

### B. Flood forecasting (30–60 minute target)
- Present 30-, 45-, and 60-minute horizons as prototype estimates.
- Show uncertainty/confidence, input freshness, coverage, and model/data limitations.
- Avoid unsupported certainty; unavailable or stale inputs must be surfaced rather than silently treated as current.

### C. Geo-targeted alerts
- Draft an alert for a selected geographic area and severity.
- Persist simulated alert records and show delivery state accurately.
- Do not claim real public delivery; live broadcast requires authorized integrations and operational approval.

### D. Incident and rescue management
- Create and update incident records with location, severity, source, timestamp, verification status, and needs.
- Track rescue mission assignment, status, timestamps, and outcome records.
- Keep an audit history for consequential changes as the system matures.

### E. Verified volunteer coordination
- Define verification status, skills, service area, availability, and consent before matching.
- Keep unverified volunteers separate from dispatch-ready resources.
- Require authorized human approval before assignments are treated as operational.

### F. Supervisor agent / task queue
- Summarize incoming reports, identify missing fields or conflicts, and suggest priorities.
- Explain why a task is recommended and link to the source records.
- Keep the agent advisory; a human supervisor approves dispatch, alert escalation, or closure.

### G. Nearby facility search
- Search by facility category such as shelter, hospital, fire/rescue station, or relief point.
- Show distance, source, verification/freshness, and accessibility/availability when known.
- Never infer that a facility is open or has capacity without current verified data.

### H. Flood-level and image intake
- Accept authorized water-level observations and image uploads with location/time where consented.
- Store metadata and analysis status.
- Integrate a trained computer-vision model only after dataset licensing, evaluation, and failure-mode review.

## 6. Out of scope for the initial MVP

- Certified or authoritative flood warnings.
- Guaranteed SMS/cell broadcast, satellite, mesh, or offline communications.
- Autonomous rescue dispatch or unreviewed AI decisions.
- Production identity verification, payment, or national ID collection.
- Claims of model accuracy before reproducible evaluation.
- Drone intelligence system (explicitly excluded from this project scope).

## 7. Constraints and assumptions

- The first geography is Bengaluru and nearby flood-prone areas of Karnataka.
- Prototype UI and records may use simulated data; each simulated item must be labelled.
- Public feeds may require credentials, agreements, rate-limit handling, and data-use review.
- Current starter stack is React + TypeScript + Vite and FastAPI + Python with SQLite persistence.
- The frontend build is not yet confirmed after a clean dependency install.

## 8. Product risks

- False positives/negatives in forecasts or image analysis.
- Stale, incomplete, or geographically mismatched input data.
- Misleading alert-delivery or facility-availability status.
- Privacy risks from location, survivor, or volunteer data.
- Unauthorized access or accidental dispatch based on demo records.

Mitigations: visible provenance/freshness, uncertainty display, human review, role-based access, audit logging, data minimization, and clear demo/production separation.
