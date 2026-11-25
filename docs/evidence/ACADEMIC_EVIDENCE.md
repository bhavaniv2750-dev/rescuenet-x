# Technical evidence for the VTU report and synopsis (S0 to G-A)

Every statement below is checkable in the repository, the test suites or the screenshot folders named. The document contains **no** performance claims for real
deployments, **no** operational partnerships, **no** real-world deployment and **no** flood-prediction accuracy beyond the dataset-bound figures in section 10,
which are kept apart from software test results. The report and synopsis themselves are not edited here.

## 1. System architecture
```
Browser (React 19 + TypeScript, one app, two shells)            Server (FastAPI, one process)                 Storage
  Public portal  /  and  /public/*   ----- HTTPS/JSON ------>   routers: auth, mfa, invitations, agencies,    SQLite (Alembic head 0006)
  Operations console  /console/*                                incidents, public, media, alerts, teams,      uploads/ (private evidence)
  shared: sign-in, account, API client, session                 volunteers, facilities, records, agents,      backups/ (verified, pre-migration)
  access token in memory, refresh token in HttpOnly cookie      flood, datasets, vision, diagnostics
                                                                core: permissions, navigation, sessions, MFA, rate limits, audit
```
* One authorisation source: `backend/app/core/permissions.py` (role to permission) enforced by `backend/app/api/deps.py` on every endpoint. The frontend never decides access:
  `backend/app/core/navigation.py` derives the experience, capabilities and navigation from the same permissions and the authentication state; the frontend renders it.
* Optional local LLM supervisor (Ollama) is **not** part of the verified system: without it a deterministic rule-based triage runs and the UI says so.

## 2. Technology stack
Backend: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, SQLite, PyJWT, pyotp (TOTP), segno (QR), cryptography (AES-256-GCM), scikit-learn (RandomForest), onnxruntime + Pillow (photo analysis), pytest.
Frontend: React 19, TypeScript, Vite, Leaflet, lucide-react, bundled fonts (Inter, JetBrains Mono), Vitest + Testing Library. Map tiles: OpenStreetMap (internet required; overlays still render offline, offline basemaps are not implemented).

## 3. Database schema (22 tables, revisions 0001 to 0006)
`users, auth_sessions, refresh_tokens, auth_challenges, mfa_credentials, mfa_recovery_codes, one_time_tokens, notification_outbox, rate_limit_events, invitations, agencies,
incidents, media_assets, alerts, rescue_teams, volunteers, facilities, beacons, rescue_records, supervisor_tasks, dataset_registry, audit_logs`.
Revisions: 0001 baseline, 0002 public references + media, 0003 sessions, 0004 contact verification + recovery + rate limits, 0005 MFA, 0006 agencies, invitations, activation flags.
Each revision is tested for upgrade, downgrade/upgrade, automatic pre-migration backup and restore (`backend/tests/test_migrations.py`). Secrets are never stored in clear
(password PBKDF2-SHA256, tokens and codes hashed/HMACed, TOTP secrets AES-GCM encrypted with environment keys).

## 4. API architecture
104 HTTP operations under `/api` (counted from the OpenAPI document). Every operation has an explicit authorisation expectation in `backend/tests/test_endpoint_authorization.py`, which calls each
one as an anonymous caller and as each of the seven roles and compares against a golden file. New in F1: `POST /api/auth/login` accepts `portal: "auto"` (default); the portal is derived from the verified account.

## 5. Authentication workflow
Sign-in (email or username + password) -> if MFA is enabled a single-use challenge (no session yet) -> TOTP code or recovery code -> session: 15-minute access token bound to a server-side session
(held in memory by the browser) + single-use rotating refresh token in an HttpOnly, SameSite=Strict cookie, CSRF double-submit + Origin check. Sessions end on password change, role/team change,
deactivation or administrator revocation; the browser then returns to the sign-in page, which says the session ended. Rate limits (database-backed) apply to sign-in, registration, verification,
recovery and invitation endpoints. Password recovery and email verification use hashed, expiring, single-use codes; email delivery is a development outbox or SMTP, and a server without a provider reports email as unavailable.

## 6. MFA workflow
Mandatory for administrators, developers, commanders, operators and rescue officers; optional for citizens and volunteers. Enrolment: current password -> QR/setup key (shown once, never logged) -> confirm with a code ->
ten single-use recovery codes (shown once). Replay of a code is refused, recovery codes are single-use, password recovery never removes MFA, and host-level MFA reset needs a recorded reason and identity re-verification.
Sensitive actions require a recent second factor.

## 7. Invitation and agency architecture
Privileged accounts exist only through (a) the host-authorised first-administrator script or (b) a host-issued, single-use, expiring, recipient-bound invitation. Activation order: owner password -> emailed code ->
mandatory MFA -> permissions; before that the account has no permissions and no navigation. Agencies (five generic categories, no real affiliation) are organisational metadata, not a security boundary.
Details: `docs/security/S5_ACCOUNTS_AGENCIES.md`.

## 8. Public portal workflow
Guest or citizen/volunteer opens `/` or `/public/*`: flood warnings (labelled SIMULATED where seeded), shelters with distance, river gauge thresholds (no live reading is claimed), forecasting scenario tool,
tracking by reference + tracking code, emergency numbers. Reporting: category, severity, description, location (preset, device location, or map click), optional photo (size, type and decoded-pixel limits, private storage), submission;
a receipt (reference + one-time tracking code, copy/save instructions) appears **only after the server confirms** the report. Citizens see their own reports; volunteers see their verification status and contact verification.
Public users see no operational controls (tested in `shells.test.tsx` and by the server's permissions).

## 9. Professional console workflow
Staff sign in with MFA and land on the page the server names: rescue officer `/console/missions`; operator and commander `/console/overview`; administrator `/console/admin`; developer `/console/diagnostics`.
Incident lifecycle: reported -> verification -> queue -> supervisor triage -> **commander approval for incidents with 5+ victims or HIGH/CRITICAL severity** -> dispatch with squad assignment -> in transit -> on scene -> resolved.
Nothing is dispatched automatically; the atomic dispatch and approval gate are covered by 66 P0 tests. Administrators and developers hold identity/diagnostic permissions only, never dispatch, triage, approval or alert publication.

### Final role-specific navigation matrix (server-decided; golden file `backend/tests/golden/navigation_matrix.json`)
| Role | Experience | Landing | Navigation entries (decided by the server) |
|---|---|---|---|
| Guest | Public | `/` | Home, Flood Digital Twin, Flood Forecasting, Emergency Alerts, Facilities & Shelters, Report Emergency |
| Citizen | Public | `/` | Home, Flood Digital Twin, Flood Forecasting, Emergency Alerts, Facilities & Shelters, Report Emergency, My Reports, My Account |
| Volunteer | Public | `/` | Home, Flood Digital Twin, Flood Forecasting, Emergency Alerts, Facilities & Shelters, Report Emergency, My Reports, My Account |
| Rescue officer | Professional | `/console/missions` | My Missions, Emergency Alerts, Flood Digital Twin, Flood Forecasting, Facilities & Shelters, Rescue Records, Report Emergency, My Account |
| Operator | Professional | `/console/overview` | Overview, Rescue Operations, AI Supervisor, Emergency Alerts, Flood Digital Twin, Flood Forecasting, Data & Models, Volunteer Coordination, Facilities & Shelters, Rescue Records, Incident Reports, My Account |
| Commander | Professional | `/console/overview` | Overview, Rescue Operations, AI Supervisor, Emergency Alerts, Flood Digital Twin, Flood Forecasting, Data & Models, Volunteer Coordination, Facilities & Shelters, Rescue Records, Incident Reports, Audit Log, My Account |
| Administrator | Professional | `/console/admin` | Emergency Alerts, Flood Forecasting, Data & Models, Facilities & Shelters, Admin Console, Agencies & Invitations, Audit Log, Diagnostics, Settings, My Account |
| Developer | Professional | `/console/diagnostics` | Data & Models, Diagnostics, My Account |


## 10. Implemented modules
Public: Home, Flood Digital Twin, Flood Forecasting, Emergency Alerts, Facilities & Shelters, Report Emergency, My Reports, My Account.
Console: Overview (mission control), Rescue Operations, My Missions, AI Supervisor, Emergency Alerts, Flood Digital Twin, Flood Forecasting, Data & Models, Volunteer Coordination, Facilities & Shelters,
Rescue Records, Incident Reports, Admin Console, Agencies & Invitations, Audit Log, Diagnostics, Settings, My Account.
Data provenance: seeded incidents, alerts, facilities, teams and LoRa SOS packets are labelled SIMULATED; catchment polygons and gauge thresholds are HISTORICAL; gauges have no live reading; nothing is labelled LIVE.

## 11. Test results
### 11a. Software regression tests (functionality and security; not machine-learning metrics)
| Suite | Result |
|---|---|
| Complete backend suite (throw-away database) | **782 passed**, 1 skipped (live Ollama, skipped because none is reachable) |
| P0 dispatch safety (`test_p0_safety` + `test_team_selection`) | 66 passed |
| S0 private media and public references (`test_public_media` + `test_public_refs`) | 53 passed |
| S5 invitations, agencies, bootstrap/demo scripts, start-up validation | 69 passed |
| S6 workspaces/navigation + endpoint authorization matrix + migrations | 52 passed |
| F1 auto-portal login tests (inside `test_auth.py`) | 3 added |
| Frontend unit/component tests (`npm test`: design components, navigation helpers, shells, login, receipt, route screens) | 28 passed |
| Frontend production build | passes |
| `pip-audit` (backend requirements) / `npm audit --omit=dev` | no known vulnerabilities / 0 vulnerabilities |
| Scripted browser verification on a fresh database (`docs/evidence/GA/browser_run.txt`) | guest report + tracking, citizen and volunteer registration and workspaces, all five staff roles, every console page per role, unauthorized direct navigation, session revocation, invitation + contact verification + mandatory MFA, private media (anonymous 401), approval gate (operator refused 403), 360 to 768 px layouts: all passed; only deliberately provoked 401s logged |
| Responsive sweep, every role and page at 360, 390, 768, 1024, 1366, 1440, 1920 px | horizontal overflow found on 4 pages (Facilities, Data & Models, Overview, AI Supervisor at phone widths) and fixed; the final sweep of the other roles reported none |
Existing tests were changed only as listed in `docs/security/S5_ACCOUNTS_AGENCIES.md` section 11 and `docs/evidence/S6/EVIDENCE.md`; no assertion was weakened.

### 11b. Machine-learning evaluation (separate; describes ONE dataset only)
From the served flood-risk model's own evaluation record (`/api/flood/forecast`): RandomForest (100 trees, depth 6, balanced classes), 1,000 records supplied with the project (800 train / 200 hold-out):
hold-out accuracy 97.0 %, precision 91.1 %, recall 95.3 %, ROC-AUC 0.994, 5-fold CV accuracy 97.5 % (sd 0.6). Honest-evaluation suite: all inputs including water level 100 % (label leakage, because the label is "water level above 4.21 m");
weather-only (the served model) 97.5 %; with 0.5 m gauge noise 97.5 %; next-hour forecasting 61.6 % accuracy / ROC-AUC 0.51, i.e. close to chance. These figures are **not** evidence of performance on real events, the data's collection method is not independently
verified, and the +30/+45/+60 minute values shown in the app are a fixed heuristic formula, not model predictions. The model was not retrained in this work.

## 12. Screenshots
`docs/evidence/GA/` (final, sanitized): `auth/` login, registration, MFA enrolment/QR/recovery codes (blurred), MFA challenge, unauthorized, session ended, invitation, contact verification;
`public/` home, guest reporting, receipt (reference and code blurred), tracking, citizen and volunteer workspaces, public module pages; `console/` every module for every role; `mobile/` 360 to 768 px views.
Earlier milestone evidence: `docs/evidence/S0` to `S6`, `F1`. No password, QR secret, recovery code, tracking code or private photograph is visible; the evidence photo is a synthetic test image and is additionally blurred.
Screenshots show development-fixture accounts that are labelled "(Demo)". `docs/evidence/GA/browser_run.txt` is the unedited log of the scripted browser run.

## 13. Security controls (summary; each has tests)
Central permission matrix; server-side sessions with revocation; HttpOnly refresh cookie, in-memory access token, CSRF; mandatory privileged MFA with encrypted secrets; verified-contact requirement; invitations instead of passwords handed out;
no built-in credentials, host-authorised bootstrap and demo-account disabling tool; production start-up validation; private evidence (authenticated media only, anonymous requests get 401); guest report limits and rate limiting;
audit log of administrative and security events; honest provenance labels; dependency audit (`pip-audit`) clean at the time of the run.

## 14. Known limitations
* All operational data is simulated or public; no real emergency service, authority or partner is connected; no real-world deployment exists.
* Email delivery to a real mailbox and SMTP were not verified; SMS, push notifications and phone verification do not exist.
* The language-model supervisor was not verified against a live Ollama server (the sandbox cannot reach one); the rule-based fallback always requires commander approval.
* Agency is metadata, not tenant isolation. SQLite is single-node. Offline basemaps are not implemented. No live river-level feed.
* The +30/+45/+60 minute scenarios are heuristic. Forecast metrics are dataset-bound and the dataset's origin is not independently verified.
* The Windows guide (`docs/WINDOWS_LOCAL_GUIDE.md`) has not been executed on a Windows machine.
* Frontend verification is scripted browser runs plus 28 unit/component tests; there is no continuous browser test suite in the repository.

## 15. Future enhancements (not started)
Alert draft/review/approve workflow and real delivery channels; live gauge integration; real mailbox verification; PWA/Capacitor/desktop packaging; mobile app; verified Ollama integration; hard multi-agency isolation; model retraining on independently verified data.
