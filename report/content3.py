from rb import *

def build_ch5(b):
    b.chapter(5, 'System Tools')
    b.h2('5.1 Introduction')
    b.p('The platform is a full-stack web application. Its components were chosen to be free, widely used and runnable on one ordinary computer, and to make the security and testing goals practical. Table 5.1 summarises the layers, and the following sections explain how each tool is used.')
    b.tbl('Technology Stack Components', ['Layer', 'Technology', 'Purpose'], [
        ['Back end', 'Python 3.13, FastAPI, Uvicorn, Pydantic v2', 'REST API, request validation, automatic OpenAPI documentation'],
        ['Persistence', 'SQLAlchemy 2, Alembic, SQLite', 'Object-relational mapping, versioned migrations, single-file database'],
        ['Machine learning', 'scikit-learn, NumPy, joblib', 'Random Forest training, evaluation and model file'],
        ['Computer vision', 'ONNX Runtime, Pillow, CLIP ViT-B/32, SegFormer-B0', 'Flood photo analysis on CPU'],
        ['Security', 'PyJWT, pyotp, segno, cryptography, hashlib (PBKDF2)', 'Access tokens, TOTP, QR codes, AES-GCM secrets, password hashing'],
        ['Front end', 'React 19, TypeScript, Vite', 'Single-page application, type-safe views, fast builds'],
        ['Mapping', 'Leaflet, leaflet.markercluster, CARTO and OpenStreetMap tiles, Natural Earth, BBMP wards', 'Interactive map, clustering, online and offline base maps'],
        ['Interface', 'lucide-react icons, bundled Inter and JetBrains Mono fonts, CSS design tokens', 'Consistent light and dark themes, no runtime CDN dependency'],
        ['Testing', 'pytest, Vitest, Testing Library, Playwright', 'Unit, API, component and scripted browser tests']], widths=[1.8, 4.2, 4.6], size=9.5, bold_first=True)
    b.h2('5.2 Backend Development Tools')
    b.p('**FastAPI** provides asynchronous REST endpoints with automatic validation through Pydantic v2 schemas and interactive API documentation. Dependency injection is used for the database session, the current user and the permission guard, which keeps authorisation in one place: a route declares the permission it needs and a shared dependency enforces it using the user’s current role read from the database on every request. **SQLAlchemy 2** maps the 22 tables to Python classes and **Alembic** versions the schema; each of the six revisions is tested for upgrade, downgrade, an automatic backup before migration and restore. **SQLite** stores all records in one file, which makes the platform easy to install in a control room or a laboratory, at the price of single-node operation.')
    b.h2('5.3 Machine Learning and Vision Tools')
    b.p('The Random Forest is trained with **scikit-learn** and saved with **joblib**, together with its evaluation record, so the service loads it once at start-up and answers in milliseconds. The photo analysis runs two published models through **ONNX Runtime** on the CPU, with **Pillow** for decoding and validation; the model weights are downloaded on first use and are not stored in the repository. An optional local language model supervisor through Ollama exists in the code, but it is not part of the verified system: without it a deterministic rule-based triage runs and the interface says so.')
    b.h2('5.4 Frontend Development Tools')
    b.p('The front end is a React 19 single-page application written in TypeScript and bundled with Vite. One application serves two shells, the public portal and the operations console; the server decides which one a user receives. **Leaflet** with **leaflet.markercluster** draws the map: incidents, squads, facilities and gauges as clustered markers, catchments as polygons and alerts as circles. A small design-token layer provides colours, spacing and elevation for both light and dark themes, and shared components (buttons, tables, dialogs, badges, page headers) keep every page consistent. Fonts and map styles are bundled locally so that nothing essential is fetched from a CDN at run time.')
    b.h2('5.5 Database and Storage Tools')
    b.p('Operational data lives in the SQLite database. Uploaded evidence photographs are stored in a private uploads directory, never in a public path, and served only to authorised callers. Verified database backups are written before each migration. A small registry table records the datasets used and their record counts for the Data & Models view.')
    b.h2('5.6 Authentication and Security Tools')
    b.p('Passwords use PBKDF2-SHA256 from the Python standard library. Access tokens are JSON Web Tokens signed with **PyJWT** and bound to a server-side session so they can be revoked. **pyotp** implements TOTP (RFC 6238); **segno** draws the QR code for enrolment; **cryptography** encrypts TOTP secrets with AES-256-GCM. Rate limiting counts events in the shared database. Dependency vulnerabilities were checked with pip-audit and npm audit, which reported no known issues at the time of the final run.')
    b.h2('5.7 Development and Testing Tools')
    b.p('Back-end behaviour is tested with **pytest** against a throw-away database. Front-end components are tested with **Vitest** and Testing Library. Scripted end-to-end runs with **Playwright** (Chromium) drive the real application on a fresh database, sweep every page for every role at six screen widths in light and dark themes, and capture the screenshots used in Chapter 9. Git with a protected main branch records the work, and generated models, uploads, databases and large map data are kept out of version control.')

def build_ch6(b):
    b.chapter(6, 'System Design')
    b.p('This chapter presents the design of the platform: its architecture, the server-driven workspace, data flows, input and output design, the object model, use cases, interaction sequences, the incident states, the operational workflow, the database schema, the security and map designs and the core algorithms.')
    b.h2('6.1 System Architecture')
    b.p('The architecture has three tiers (Figure 6.1). The client tier is one React application with two shells. The application tier is a single FastAPI process containing 22 router modules, a core layer for permissions, workspaces, sessions, MFA, rate limits and audit, and domain services for the incident lifecycle, atomic dispatch, alerting, the flood model, photo analysis, catchment parsing and geodesy. The data tier holds the SQLite database, the private uploads directory, verified backups and the datasets. Online map tiles, SMTP and a language-model runtime are optional external services. The platform exposes 104 HTTP operations under /api.')
    b.fig('fig/f_arch.png', 'Overall system architecture', 12.8, 19)
    b.h2('6.2 Server-Driven Workspace and Navigation')
    b.p('The front end never decides who may see what. After sign-in it asks the server for the user’s workspace, which contains the experience (public or professional), the capabilities the interface may offer, the navigation entries with their paths, and the landing page (Figure 6.2). The same permission matrix that guards each endpoint produces this answer, so the interface and the API cannot disagree. A page that the server did not offer cannot be opened: the user receives a genuine 404 for an unknown address or a clear no-access screen for a known address outside their workspace. Table 6.1 summarises the resulting navigation for each role.')
    b.fig('fig/f_workspace.png', 'Server-driven workspace: the backend decides what each caller can see', 14.2)
    b.tbl('Role, Workspace, Landing Page and Navigation Size (from the golden navigation matrix)', ['Role', 'Experience', 'Landing', 'Entries', 'Permissions'], [
        ['Guest', 'Public', '/', '6', 'public read, report'], ['Citizen', 'Public', '/', '8', '7'], ['Volunteer', 'Public', '/', '8', '7'], ['Rescue officer', 'Professional', '/console/missions', '8', '14'],
        ['Operator', 'Professional', '/console/overview', '12', '28'], ['Commander', 'Professional', '/console/overview', '13', '33'], ['Administrator', 'Professional', '/console/admin', '10', '13'], ['Developer', 'Professional', '/console/diagnostics', '3', '8']], widths=[2.2, 2.2, 3.2, 1.2, 2.6], size=9.5, bold_first=True)
    b.h2('6.3 Data Flow Diagrams')
    b.p('The context diagram (Figure 6.3) shows the platform as one process exchanging data with the guest or citizen, the volunteer, the rescue officer, the operator, the commander, the administrator, the developer, the map tile providers and the datasets. The level-1 diagram (Figure 6.4) decomposes it into nine processes: authentication and session, incident intake and evidence, verification and lifecycle, flood risk and scenario outlook, triage and commander approval, dispatch and rescue records, alerts and notifications, volunteers squads and facilities, and audit and diagnostics. Seven data stores hold users and sessions, incidents and media, teams and records, alerts, facilities and volunteers, the audit log, and the datasets with the model files.')
    b.fig('fig/f_dfd0.png', 'Context diagram (DFD level 0)', 13.6)
    b.fig('fig/f_dfd1.png', 'Detailed data flow diagram (DFD level 1)', 14.4, 18)
    b.h2('6.4 Input and Output Design')
    b.p('Table 6.2 summarises the inputs of the system, how each is validated and processed, and the outputs produced.')
    b.tbl('Input and Output Design Specification', ['Input', 'Validation and processing', 'Output'], [
        ['Sign-in credentials and TOTP code', 'Rate limit, PBKDF2 check, replay-safe TOTP, session creation', 'Access token, refresh cookie, workspace, audit entry'],
        ['Emergency report with optional photo', 'Schema validation, size / type / pixel limits, EXIF read, private storage, guest limits', 'Incident REPORTED, receipt with reference and one-time code, photo analysis'],
        ['Scenario inputs (rain, water, humidity, temperature)', 'Schema bounds, Random Forest, gauge rule', 'Probability, risk class, advisory, factors, projections'],
        ['Verification and lifecycle actions', 'Permission check, allowed-transition table', 'New state, audit entry, 403 or 409 on refusal'],
        ['Triage request', 'Haversine ranking of AVAILABLE squads and shelters with capacity', 'Supervisor task with recommendation and approval flag'],
        ['Commander approval', 'Recent MFA, signed request, gate rule', 'Atomic dispatch: squad DEPLOYED, incident DISPATCHED'],
        ['Alert definition', 'Duplicate check, severity and area', 'Alert record, CAP 1.2 XML, escalation level'],
        ['Invitation and agency actions', 'Admin permission, hashed single-use token, expiry', 'Pending account, activation steps (contact, MFA)'],
        ['Datasets (catchments, gauges, CSV)', 'Shapefile parser, CSV reader, registry', 'GeoJSON polygons, gauge list, model training record']], widths=[2.8, 4.6, 3.6], size=9.2, bold_first=True)
    b.h2('6.5 UML Class Diagram')
    b.p('Figure 6.5 shows the principal domain classes and their relationships. Users belong to an agency and own sessions; incidents have media assets, supervisor tasks and rescue records, and may be assigned to a rescue team or a volunteer; supervisor tasks may suggest a facility; alerts and the audit log stand alone and are referenced by identifier. Incident carries the lifecycle operations and the approval rule.')
    b.fig('fig/f_class.png', 'UML class diagram of the core domain entities', 13.6, 17.5)
    b.h2('6.6 Use Case Diagram')
    b.p('Figure 6.6 shows eight actors and fifteen use cases. Public actors read flood information, report and track emergencies and register. Staff actors sign in with MFA and perform only the use cases their role allows; the administrator and developer have no operational use cases.')
    b.fig('fig/f_usecase.png', 'Use case diagram', 13.2, 17.5)
    b.h2('6.7 Sequence Diagrams')
    b.p('Figure 6.7 traces an emergency from the report to the dispatch. The report is validated and stored with a private photo, the reporter gets a receipt, the operator verifies the incident, the supervisor service proposes the nearest squad and shelter and applies the gate rule, a commander approves with a recent second factor, and the dispatch service changes the squad and incident in one transaction. An operator cannot dispatch a gated incident: the endpoint answers 403 and the state machine would answer 409. Figure 6.8 shows the sign-in sequence with multi-factor authentication.')
    b.fig('fig/f_seq_incident.png', 'Emergency incident sequence from report to dispatch', 14.0, 18)
    b.fig('fig/f_seq_auth.png', 'Sign-in sequence with multi-factor authentication', 14.0)
    b.h2('6.8 State Transition Diagram')
    b.p('An incident moves from REPORTED through UNDER VERIFICATION, VERIFIED, QUEUED and TRIAGE IN PROGRESS to PENDING APPROVAL when the gate applies, and then to DISPATCHED, IN TRANSIT, ON SCENE and RESOLVED (Figure 6.9). Below the gate the operator confirms and the incident goes straight to DISPATCHED. A declined dispatch becomes REJECTED and can be re-queued; DUPLICATE and CANCELLED are terminal. The allowed transitions are a table in the service layer, and a test walks every state pair.')
    b.fig('fig/f_state.png', 'Incident state transition diagram', 14.2)
    b.h2('6.9 Activity Diagram')
    b.p('Figure 6.10 shows the two operational lanes. In the flood-risk lane, scenario inputs are clipped to the model range, the Random Forest gives a probability, the gauge rule is applied, the higher class is chosen, projections are computed and the page is shown with provenance labels. In the incident lane, a report is received, verified, triaged and, where the gate applies, approved by a commander before an atomic dispatch and the mission record.')
    b.fig('fig/f_activity.png', 'Activity diagram for the operational workflow', 13.4, 18)
    b.h2('6.10 Database Schema')
    b.p('The database has 22 tables created by six Alembic revisions (Figure 6.11, Table 6.3). Identifiers use readable prefixes, and operational tables carry a data label. Secrets are never stored in clear: passwords use PBKDF2, tokens and codes are hashed, and TOTP secrets are encrypted.')
    b.fig('fig/f_er.png', 'Entity relationship overview of the 22 tables', 13.6, 18.5)
    b.tbl('Database Tables', ['Group', 'Tables'], [
        ['Identity and access', 'users, auth_sessions, refresh_tokens, auth_challenges, mfa_credentials, mfa_recovery_codes, one_time_tokens, notification_outbox, rate_limit_events, invitations, agencies'],
        ['Incidents and evidence', 'incidents, media_assets, beacons, supervisor_tasks, rescue_records'],
        ['Resources', 'rescue_teams, volunteers, facilities, alerts'],
        ['Governance and data', 'audit_logs, dataset_registry']], widths=[2.4, 8.6], size=9.5, bold_first=True)
    b.p('Revision 0001 is the baseline, 0002 adds public references and media, 0003 sessions, 0004 contact verification, recovery and rate limits, 0005 multi-factor authentication, and 0006 agencies, invitations and activation flags.')
    b.h2('6.11 Security Design')
    b.p('Every endpoint is protected by the same chain (Figure 6.12). The access token is checked and its session confirmed active; the user’s current role is read from the database, not from the token, so role changes and deactivation apply immediately; the endpoint’s required permission is checked against the permission matrix; sensitive actions additionally require a recent second factor; and consequential actions write an audit entry. An endpoint-authorisation test calls each of the 104 operations as an anonymous caller and as each of the seven roles and compares the answers with a stored golden file, so a new endpoint without an explicit expectation fails the suite.')
    b.fig('fig/f_perm.png', 'Authorization flow applied to every endpoint', 14.0)
    b.h2('6.12 Map and Offline Design')
    b.p('The map selects its base layer through a chain of availability checks (Figure 6.13). The chip on the map names the active source, and users can override the automatic choice in the map settings. Operational overlays do not depend on the base map, so they remain correct when tiles are unavailable. An optional regional vector-tile archive (PMTiles) was prepared as a further offline source; it is verified only on a small synthetic fixture and is not part of the verified coverage claims.')
    b.fig('fig/f_basemap.png', 'Base-map availability chain', 14.2)
    b.h2('6.13 Algorithmic Specifications')
    b.p('Three algorithms form the analytical and safety core. Algorithm 1 turns inputs into a risk class, Algorithm 2 computes the scenario projections and Algorithm 3 proposes resources and applies the approval gate.')
    b.code('Algorithm 1: PredictFloodRisk', '''01 function PredictFloodRisk(rain, water, humidity, temp):
02     x <- [rain, humidity, temp]                 # water level is NOT a model input
03     P <- RandomForest.predict_proba(x)[flood]   # mean of 100 tree probabilities
04     if P >= 0.75 or water >= 5.5: cls <- CRITICAL
05     elif P >= 0.50 or water >= 3.8: cls <- HIGH
06     elif P >= 0.25 or water >= 2.5: cls <- MODERATE
07     else: cls <- LOW
08     gauge_rule <- (water > 4.21)                # reported separately as a factor
09     return (cls, P, advisory(cls), gauge_rule)''')
    b.p('**Algorithm 1** computes the probability from the three weather inputs only (line 02 and 03) and lets the water level raise the class through fixed thresholds (lines 04 to 07). Each tree makes at most six comparisons, so a prediction costs about six hundred comparisons and completes in milliseconds. Line 08 records whether the dataset label rule is met, which is shown to the operator as the factor with no model weight.')
    b.code('Algorithm 2: ProjectScenario', '''01 function ProjectScenario(P, rain):
02     surge <- (rain / 100) * 0.15
03     for (t, k) in [(30, 0.5), (45, 0.9), (60, 1.3)]:
04         out[t] <- clip(P + k * surge, 0.01, 0.99)
05     return out         # labelled: heuristic scenario projection, not a forecast''')
    b.p('**Algorithm 2** is a constant-time arithmetic adjustment. It uses no sensor series and no trained model, which is why the result is labelled as a heuristic scenario projection throughout the interface.')
    b.code('Algorithm 3: TriageAndGate', '''01 function TriageAndGate(incident I, squads S, shelters F):
02     best_s <- nearest s in S with s.status == AVAILABLE      # Haversine distance
03     best_f <- nearest f in F with (f.capacity - f.occupancy) >= I.people
04     (sev, ppl) <- EffectiveRisk(I)   # recorded assessment; edits can only raise it
05     needs <- (ppl >= 5) or (sev in {HIGH, CRITICAL})
06     task <- SupervisorTask(I, best_s, best_f, requires_human_approval = needs)
07     if needs: I.status <- PENDING_APPROVAL           # nobody is dispatched
08     return task''')
    b.p('**Algorithm 3** examines every squad and shelter once, so its cost grows linearly with their number. The gate (lines 04 to 07) is ordinary code that runs after the recommendation. If a commander later approves, the dispatch service performs the atomic change; if a commander declines, the incident becomes REJECTED and can be re-queued.')
    b.h2('6.14 Deployment View')
    b.p('For development, demonstration and a single control room, the browser, the Uvicorn and FastAPI process, the SQLite file, the uploads directory and the model files run on one machine (Figure 6.14). Map tile providers, SMTP and a language-model runtime are optional and outside the host. The same layout is used in the Windows guide that accompanies the project, which has not been executed on a Windows machine in this work.')
    b.fig('fig/f_deploy.png', 'Local deployment view', 14.0)
