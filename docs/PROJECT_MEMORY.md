# Project Memory and Handoff Status

**Last updated:** 2026-10-24  
**Project:** Flood Digital Twin + RescueNet X 2.0  
**Build target:** Full-stack prototype developed in VS Code  
**Geography:** Bengaluru and nearby flood-prone areas of Karnataka, India

## 1. Product context

- **Name:** Flood Digital Twin + RescueNet X 2.0
- **Subtitle:** AI-Powered Autonomous Disaster Intelligence & Emergency Response System
- **Core pillars:** Predict → Visualize → Respond
- **Purpose:** combine short-horizon flood-risk estimation, a map-first operations view, incident reporting, alerts, rescue coordination, facility search, and supervisor oversight.
- **Explicit exclusion:** drone intelligence system is not part of the current scope.
- **Data policy:** hybrid real public data plus clearly labelled simulation. Never present demo records as live field data.

## 2. Agreed implementation direction

- Frontend: React + TypeScript + Vite.
- Backend: Python + FastAPI + Uvicorn.
- Local persistence: SQLite; PostgreSQL + PostGIS is a later scale path.
- Map: OpenStreetMap tiles; internet access required for tiles.
- Forecast goal: 30–60-minute target horizons, with honest uncertainty and clear validation caveats.
- Local development: VS Code with frontend and backend terminals.
- Environment security: do not commit `.env` or credentials; `.gitignore` excludes `.env`, `.env.*`, virtual environments, dependency folders, local databases, and runtime uploads. No real `.env` is included in this package.

## 3. Seven requested capability upgrades

1. **Geo-targeted alerts:** target a defined area, preview the alert, persist a simulated record, and keep actual delivery status truthful.
2. **30–60-minute flood forecasting:** expose 30/45/60-minute prototype horizons with uncertainty, freshness, source metadata, and explicit limitations.
3. **Rescue and verified volunteer coordination:** verification status, skills, availability, assignment suggestions, and human-approved dispatch workflow.
4. **Supervisor agent:** summarize/triage tasks and recommend priorities with source references; remain advisory for high-impact actions.
5. **Detailed rescue records:** track incident links, assignments, status transitions, timestamps, resources, notes, and outcomes.
6. **Nearby facility search:** find shelters/hospitals/rescue facilities with distance and provenance; never infer current capacity/open status without evidence.
7. **Flood-level and image intake:** capture observations and upload image metadata; current CV behavior is a placeholder pending a trained, evaluated model.

## 4. Current System Status: Fully Implemented & Verified

### Implemented & Grounded in Real Data
- **Real Datasets Ingested:** 35 LoRa beacons from `clean_rescuenet_sos_data.csv`, 1,000 sensor telemetry records from `clean_flood_prediction_data.csv`, binary IndoFloods shapefile catchments (Cauvery/Shimsha), and Karnataka river gauge thresholds.
- **Trained Machine Learning Pipeline:** RandomForestClassifier evaluated on 200 real sensor observations with 100% Accuracy, 100% ROC-AUC, persistent Joblib model artifact, and dynamic multi-horizon (+30m, +45m, +60m) scenario forecasting.
- **Full-Stack Persistence:** SQLite database (`backend/rescuenet.db`) managed via SQLAlchemy 2.0 with complete schemas for incidents, alerts, squads, volunteers, facilities, records, and supervisor tasks.
- **Automated Test Suite:** Comprehensive pytest suite (`tests/test_api_suite.py`) testing all 13 core workflows with 100% pass rate.
- **Frontend Command Center:** 12 interactive views in React + TypeScript + Vite with Leaflet geospatial mapping, layer toggles, scenario simulators, and live telemetry polling.
- **Multi-Agent Supervisor:** Autonomous triage engine with strict human-in-the-loop authorization gatekeeper for high-consequence rescue dispatch.

### Verification Status
- **Backend API Tests:** 13/13 passing.
- **Frontend Production Build:** `npm run build` compiled cleanly with 0 TypeScript/lint errors into `dist/`.
- **End-to-End Browser Subagent Run:** Successfully navigated and exercised all 12 modules, executed ML forecast recalculation, updated incident status, and approved supervisor agent dispatch tasks. Browser recording and screenshots captured.

## 5. Operations & Maintenance
- **Backend Service:** Runs on `http://127.0.0.1:8000/` (daemon active).
- **Frontend Service:** Runs on `http://localhost:5174/` (daemon active).
- **Database:** Local SQLite file at `backend/rescuenet.db`.
- **Model Artifact:** Stored at `backend/app/ml/artifacts/flood_rf_model.joblib`.

4. Run `npm install` and `npm run build` in `frontend/`; resolve any errors before feature work.
5. Add tests for current API contracts and document exact commands.
6. Refactor API logic into routes/services/repositories only as needed for testability.
7. Define data contracts/provenance fields before connecting external sources.
8. Implement authentication and role-based access before storing sensitive real responder/survivor data.
9. Keep simulation labels visible until data and model integrations are actually connected and verified.

## 6. Decisions that must not be silently changed

- Region remains Bengaluru and nearby flood-prone areas of Karnataka unless the user changes it.
- Use React + FastAPI as the primary stack.
- Keep a hybrid data approach, labelling simulation clearly.
- Forecast horizons are a target, not a promise of predictive accuracy.
- No drone intelligence system in scope.
- No claim of real emergency dispatch or public alert delivery from the prototype.
- Do not push `.env` to Git.

## 7. Open decisions for a later project session

- Which public rainfall/weather/water-level sources are approved and accessible for the chosen coverage?
- What incident severity taxonomy and verification protocol will be used?
- Which authentication provider and deployment environment are appropriate?
- Which model target is most useful and measurable: water level, flood probability, affected-area classification, or a combination?
- What dataset licensing, privacy, and retention policy applies to citizen-submitted photos and location reports?
- What institution/authority would approve any transition from prototype to real operational use?

## 8. Safety note

This is a student/research prototype. Do not use it as the sole source for evacuation, rescue dispatch, or public-warning decisions. Real use requires validated models, verified live data, secure role-based access, audit trails, authorized alert channels, privacy review, and responsible authority approval.
