from dgm import *

# ---------- Fig 6.1 architecture
def f_arch():
    H = 92; fig, ax = canvas(H); title(ax, H, 'Overall system architecture of Flood Digital Twin and RescueNet X 2.0')
    box(ax, 2, 68, 96, 20, '', fc='#f7fafc', ec=GREY, ls='--'); ax.text(4, 85.8, 'CLIENT TIER: browser, React 19 + TypeScript + Vite (one application, two shells)', fontsize=6.2, fontweight='bold', color=TEAL, va='center')
    box(ax, 4, 70, 29, 12.5, 'Public portal\n/  and  /public/*\nflood watch, shelters, reporting,\ntracking, My Reports', fc=PALE, ec=TEAL)
    box(ax, 35.5, 70, 29, 12.5, 'Operations console\n/console/*\nOverview, Rescue Operations, Supervisor,\nAlerts, Records, Admin, Diagnostics', fc=PALE, ec=TEAL)
    box(ax, 67, 70, 29, 12.5, 'Shared client services\nsign-in, MFA, account, API client,\nin-memory access token, theme menu,\nLeaflet map (4 online + 2 offline bases)', fc=LIGHT)
    arrow(ax, (50, 68), (50, 62), 'HTTPS / JSON  (access token in memory, refresh token in HttpOnly cookie, CSRF check)', fs=5.4, off=(0, 0))
    box(ax, 2, 28, 96, 33.5, '', fc='#f7fafc', ec=GREY, ls='--'); ax.text(4, 59.2, 'APPLICATION TIER: FastAPI (one process), Pydantic v2 validation, 104 HTTP operations under /api', fontsize=6.2, fontweight='bold', color=TEAL, va='center')
    box(ax, 4, 46, 44, 11.5, 'Routers (22 modules)\nauth, mfa, invitations, agencies, incidents, public, media,\nalerts, teams, volunteers, facilities, records, agents,\nflood, datasets, vision, diagnostics, health', fc=LIGHT, fs=5.6)
    box(ax, 50, 46, 46, 11.5, 'Core security and policy\npermission matrix (role to permission), server-driven\nworkspace and navigation, server-side sessions,\nTOTP MFA, rate limits, audit log', fc=WARN, fs=5.6)
    for i, t in enumerate(['Incident lifecycle\n+ approval gate', 'Dispatch\n(atomic)', 'Alerting\nCAP 1.2 XML', 'Flood model\nRandom Forest', 'Photo analysis\nCLIP + SegFormer', 'Catchment parser\nshapefile to GeoJSON', 'Trilateration,\nHaversine']):
        box(ax, 4 + i * 13.5, 31, 12.6, 11.5, t, fc=OK if i in (0, 1) else PALE, fs=5.0)
    arrow(ax, (50, 28), (50, 22), 'SQLAlchemy 2 / Alembic', fs=5.4, off=(0, 0))
    box(ax, 2, 4, 96, 17.5, '', fc='#f7fafc', ec=GREY, ls='--'); ax.text(4, 19.3, 'DATA TIER AND OPTIONAL EXTERNAL SERVICES', fontsize=6.2, fontweight='bold', color=TEAL, va='center')
    box(ax, 4, 6, 23, 10.5, 'SQLite database\n22 tables, Alembic head 0006', fc=LIGHT, fs=5.6)
    box(ax, 29, 6, 20, 10.5, 'uploads/ (private\nevidence photos)\nbackups/ (verified)', fc=LIGHT, fs=5.4)
    box(ax, 51, 6, 22, 10.5, 'Datasets: IndoFloods\ncatchments + gauges,\nflood CSV, model files', fc=LIGHT, fs=5.4)
    box(ax, 75, 6, 21, 10.5, 'Optional / external\nOSM and CARTO tiles, SMTP,\nOllama (not verified)', fc='white', ec=GREY, ls='--', fs=5.4)
    save(fig, 'f_arch')

# ---------- workspace flow
def f_workspace():
    H = 44; fig, ax = canvas(H); title(ax, H, 'Server-driven workspace: the backend decides what each caller can see')
    xs = [2, 22, 42, 62, 82]; labels = ['Sign-in\n(password, then\nTOTP if enabled)', 'Server session\n(15 min access token,\nrotating refresh)', 'Permission matrix\n(role to 42\npermissions)', 'Workspace answer\nexperience, capabilities,\nnavigation, landing page', 'Frontend shell\nPublic portal or\nOperations console']
    for x, t in zip(xs, labels): box(ax, x, 22, 16.5, 14, t, fc=PALE if x != 42 else WARN, fs=5.5)
    for a, b in zip(xs[:-1], xs[1:]): arrow(ax, (a + 16.5, 29), (b, 29))
    box(ax, 22, 4, 56, 11, 'Every later request: access token -> session check (not revoked, not idle) -> permission check for that endpoint -> audit entry for\nconsequential actions.  A page the server did not offer cannot be opened (404 or "no access" screen).', fc=LIGHT, fs=5.4)
    arrow(ax, (50, 22), (50, 15), '')
    save(fig, 'f_workspace')

# ---------- DFD 0
def f_dfd0():
    H = 70; fig, ax = canvas(H); title(ax, H, 'Context diagram (DFD level 0)')
    ax.add_patch(Circle((50, 35), 13.5, fc=PALE, ec=TEAL, lw=1.2, zorder=2)); ax.text(50, 35, 'Flood Digital Twin\nand RescueNet X 2.0\n(0.0)', ha='center', va='center', fontsize=7, fontweight='bold', zorder=3)
    ents = [(8, 58, 'Guest / Citizen'), (8, 40, 'Volunteer'), (8, 22, 'Rescue officer'), (8, 6, 'Operator'), (92, 58, 'Commander'), (92, 40, 'Administrator'), (92, 22, 'Developer'), (50, 62, 'Map tile providers\n(OSM, CARTO)'), (50, 5, 'IndoFloods datasets,\nflood CSV, model files')]
    for x, y, t in ents: box(ax, x - 10, y - 4, 20, 8, t, fc=LIGHT, fs=5.6)
    fl = [((18, 58), (38.2, 41), 'report, tracking, sign-in'), ((38.2, 38), (18, 41), 'receipt, alerts, shelters'), ((18, 40), (36.5, 36), 'registration, verification'),
          ((18, 22), (39, 29), 'mission updates'), ((18, 6), (42, 24), 'verify, triage, alerts'), ((82, 58), (62, 41), 'approve / decline dispatch'), ((82, 40), (63.5, 36), 'users, invitations, audit'), ((82, 22), (61, 29), 'diagnostics'),
          ((50, 58), (50, 48.7), 'base-map tiles'), ((50, 9), (50, 21.3), 'datasets, model')]
    for p, q, l in fl: arrow(ax, p, q, l, fs=5.0)
    save(fig, 'f_dfd0')

# ---------- DFD 1
def f_usecase():
    H = 100; fig, ax = canvas(H); title(ax, H, 'Use case diagram')
    ax.add_patch(Rectangle((24, 3), 52, 92, fc='#fbfdff', ec=GREY, lw=0.9)); ax.text(50, 93, 'RescueNet X 2.0', ha='center', fontsize=6.5, fontweight='bold', color=NAVY)
    ucs = ['View flood watch, shelters,\ngauge thresholds', 'Report an emergency\n(with optional photo)', 'Track a report (reference + code)', 'Register, verify contact,\nenrol MFA', 'Sign in (password, TOTP)',
           'Verify / reject incident', 'Run supervisor triage', 'Approve or decline dispatch', 'Dispatch squad, update mission', 'Publish alert (CAP) and\nacknowledge', 'Manage volunteers and facilities', 'Record rescue outcome',
           'Invite users, manage agencies', 'Review audit log', 'Run diagnostics']
    ys = [86 - i * 5.6 for i in range(len(ucs))]
    for t, y in zip(ucs, ys): ellipse(ax, 50, y, 40, 4.9, t, fs=5.0)
    acts = [(9, 84, 'Guest'), (9, 66, 'Citizen'), (9, 48, 'Volunteer'), (9, 30, 'Rescue\nofficer'), (91, 80, 'Operator'), (91, 58, 'Commander'), (91, 36, 'Administrator'), (91, 16, 'Developer')]
    for x, y, t in acts: actor(ax, x, y, t, s=1.05)
    L = {'Guest': [0, 1, 2, 4], 'Citizen': [0, 1, 2, 3, 4], 'Volunteer': [3, 4, 10], 'Rescue\nofficer': [4, 8, 11], 'Operator': [4, 5, 6, 9, 10], 'Commander': [4, 6, 7, 9, 13], 'Administrator': [4, 12, 13, 14], 'Developer': [4, 14]}
    for x, y, t in acts:
        for k in L[t]:
            ax.plot([x + (2.2 if x < 50 else -2.2), 50 + (-20 if x < 50 else 20)], [y + 1.2, ys[k]], color='#9aa7b4', lw=0.5, zorder=1)
    save(fig, 'f_usecase')

# ---------- State diagram
def seq(ax, names, xs, top, bottom):
    for n, x in zip(names, xs):
        box(ax, x - 7.5, top, 15, 5.5, n, fc=PALE, ec=TEAL, fs=5.3, bold=True)
        ax.plot([x, x], [top, bottom], color=GREY, lw=0.7, ls=(0, (3, 3)), zorder=0)

def f_seq_incident():
    H = 104; fig, ax = canvas(H); title(ax, H, 'Emergency incident sequence: report to dispatch')
    names = ['Reporter', 'Public / Incident\nAPI', 'Lifecycle\nservice', 'Operator', 'Supervisor\ntriage', 'Commander', 'Dispatch\nservice']; xs = [9, 24, 40, 55, 69, 83, 95]
    xs = [8, 22, 36, 50, 64, 78, 92]; seq(ax, names, xs, 92, 4)
    msgs = [(0, 1, 'POST report (+ photo)', 86), (1, 1, 'validate, rate-limit, store photo privately', 80.5), (1, 0, 'receipt: reference + one-time code', 75), (1, 2, 'create incident = REPORTED', 69.5),
            (3, 2, 'verify (VERIFIED) or reject / duplicate', 64), (3, 4, 'request triage', 58.5), (4, 4, 'nearest AVAILABLE squad, shelter with capacity (Haversine)', 53), (4, 4, 'gate rule: 5+ victims or HIGH/CRITICAL', 47.5),
            (4, 5, 'PENDING_APPROVAL', 42), (5, 5, 'recent MFA required', 36.5), (5, 6, 'approve (signed request)', 31), (6, 6, 'squad DEPLOYED and incident DISPATCHED (one transaction)', 25.5), (6, 2, 'audit entry', 20), (6, 0, 'status visible by reference + code', 15)]
    for a, b, t, y in msgs:
        if a == b: ax.add_patch(FancyArrowPatch((xs[a], y), (xs[a], y - 3), arrowstyle='-|>', mutation_scale=6, lw=0.8, color=NAVY, connectionstyle='arc3,rad=-1.6')); ax.text(xs[a] + (4 if xs[a] < 70 else -4), y - 1.5, t, fontsize=4.9, va='center', ha='left' if xs[a] < 70 else 'right')
        else: arrow(ax, (xs[a], y), (xs[b], y), t, fs=4.9, off=(0, 1.5))
    box(ax, 4, 4, 92, 7, 'An operator cannot dispatch a gated incident: the endpoint answers 403 and the state machine answers 409. Nothing is dispatched automatically.', fc=WARN, fs=5.3)
    save(fig, 'f_seq_incident')

def f_seq_auth():
    H = 74; fig, ax = canvas(H); title(ax, H, 'Sign-in sequence with multi-factor authentication')
    names = ['Browser', 'Auth API', 'Rate limiter', 'Session store', 'MFA service']; xs = [10, 29, 48, 68, 88]; seq(ax, names, xs, 62, 4)
    msgs = [(0, 1, 'POST /auth/login (identifier, password, portal=auto)', 56), (1, 2, 'check sign-in limit', 51), (1, 1, 'verify PBKDF2 hash, lock-out counters', 46), (1, 0, 'MFA enabled: single-use challenge (no session yet)', 41),
            (0, 1, 'POST /auth/mfa/verify (TOTP or recovery code)', 36), (1, 4, 'validate code, refuse replay of the same step', 31), (1, 3, 'create session (assurance = MFA)', 26), (1, 0, 'access token (15 min) + refresh cookie (HttpOnly, SameSite)', 21), (0, 1, 'GET /auth/me: workspace (experience, navigation)', 16)]
    for a, b, t, y in msgs:
        if a == b: ax.add_patch(FancyArrowPatch((xs[a], y), (xs[a], y - 3), arrowstyle='-|>', mutation_scale=6, lw=0.8, color=NAVY, connectionstyle='arc3,rad=-1.6')); ax.text(xs[a] + (4 if xs[a] < 70 else -4), y - 1.5, t, fontsize=4.9, va='center', ha='left' if xs[a] < 70 else 'right')
        else: arrow(ax, (xs[a], y), (xs[b], y), t, fs=4.9, off=(0, 1.5))
    save(fig, 'f_seq_auth')

def f_activity():
    H = 100; fig, ax = canvas(H); title(ax, H, 'Activity diagram: flood-risk lane and incident-response lane')
    ax.add_patch(Rectangle((2, 4), 46, 88, fc='#fbfdff', ec=GREY)); ax.add_patch(Rectangle((52, 4), 46, 88, fc='#fbfdff', ec=GREY))
    ax.text(25, 89.5, 'Flood-risk lane', ha='center', fontsize=6.5, fontweight='bold', color=TEAL); ax.text(75, 89.5, 'Incident-response lane', ha='center', fontsize=6.5, fontweight='bold', color=TEAL)
    L1 = ['Scenario inputs: rainfall,\nhumidity, temperature, water level', 'Clip inputs to training range', 'Random Forest probability\n(3 weather inputs)', 'Gauge rule on water level\n(2.5 / 3.8 / 5.5 m)', 'Risk class = higher of\nmodel band and gauge band', 'Heuristic +30/+45/+60 min\nscenario projections', 'Display with SIMULATED /\nHISTORICAL labels']
    for i, t in enumerate(L1):
        y = 80 - i * 11.3; box(ax, 8, y - 3.5, 34, 7.5, t, fc=PALE if i not in (4,) else WARN, fs=5.2)
        if i: arrow(ax, (25, y + 7.8), (25, y + 4), '')
    L2 = ['Report received\n(guest or signed-in user)', 'Operator verifies (or marks\nduplicate / rejected)', 'Queue and supervisor triage\n(nearest squad and shelter)']
    for i, t in enumerate(L2):
        y = 80 - i * 11.3; box(ax, 58, y - 3.5, 34, 7.5, t, fc=PALE, fs=5.2)
        if i: arrow(ax, (75, y + 7.8), (75, y + 4), '')
    ax.add_patch(Polygon([[75, 49.5], [90, 43], [75, 36.5], [60, 43]], fc=WARN, ec=NAVY, lw=0.9)); ax.text(75, 43, '5+ victims or\nHIGH / CRITICAL?', ha='center', va='center', fontsize=5.2)
    arrow(ax, (75, 56.7), (75, 49.5), '')
    box(ax, 58, 24, 34, 7.5, 'Commander approves\n(recent MFA, signed request)', fc=WARN, fs=5.2); arrow(ax, (75, 36.5), (75, 31.7), 'yes', off=(3, 0)); arrow(ax, (90, 43), (95.5, 43), '')
    ax.plot([95.5, 95.5], [43, 16], color=NAVY, lw=0.9); arrow(ax, (95.5, 16), (92, 16), 'no: operator confirms', off=(-9, 2.6), fs=4.8)
    box(ax, 58, 12, 34, 7.5, 'Dispatch: squad DEPLOYED,\nincident DISPATCHED (atomic)', fc=OK, fs=5.2); arrow(ax, (75, 24), (75, 19.7), '')
    box(ax, 58, 5.5, 34, 5, 'En route, on scene, resolved, record', fc=PALE, fs=5.0); arrow(ax, (75, 12), (75, 10.7), '')
    save(fig, 'f_activity')

def f_perm():
    H = 40; fig, ax = canvas(H); title(ax, H, 'Authorization flow applied to every endpoint')
    xs = [2, 21, 40, 59, 78]; ts = ['Request with\naccess token', 'Token valid and\nsession active?\n(not revoked, idle)', 'Role holds the\nrequired permission?\n(permission matrix)', 'Recent MFA for\nsensitive action?', 'Handler runs;\naudit entry written']
    for x, t in zip(xs, ts): box(ax, x, 15, 18.5, 14, t, fc=WARN if x in (21, 40, 59) else PALE, fs=5.3)
    for a, b in zip(xs[:-1], xs[1:]): arrow(ax, (a + 18.5, 22), (b, 22))
    for x, t in [(30, '401'), (49, '403'), (68, '403 / step-up')]: arrow(ax, (x - 0.5, 15), (x - 0.5, 8), t, color=RED, fs=5.0, off=(3, 0))
    save(fig, 'f_perm')

def f_basemap():
    H = 52; fig, ax = canvas(H); title(ax, H, 'Base-map availability chain (automatic fallback, manual override)')
    xs = [2, 22, 42, 62, 82]; ts = ['Configured online map\n(CARTO dark / light /\nVoyager or OSM)', 'Secondary online map\n(another provider)', 'Regional offline archive\n(PMTiles, optional)', 'Basic local map\nNatural Earth + BBMP wards\n(bundled, 315 KB)', 'Explicit notice:\n"No base map available"']
    fcs = [PALE, PALE, LIGHT, OK, WARN]
    for x, t, f in zip(xs, ts, fcs): box(ax, x, 22, 16.5, 16, t, fc=f, fs=5.0, ls='--' if x == 42 else '-')
    for a, b in zip(xs[:-1], xs[1:]): arrow(ax, (a + 16.5, 30), (b, 30), 'if tiles fail', fs=4.4, off=(0, 2.3))
    box(ax, 8, 5, 84, 10, 'A tile source is abandoned after 3 tile errors without a success, or after 6 s of silence. The chip on the map always states the active source\n("Online map", "Offline map: locally stored data", "No base map available"). Overlays (markers, catchments) are drawn on every source.', fc=LIGHT, fs=5.0)
    save(fig, 'f_basemap')

def f_mlpipe():
    H = 54; fig, ax = canvas(H); title(ax, H, 'Flood-risk pipeline: from inputs to risk class and scenario projections')
    box(ax, 2, 30, 17, 14, 'Inputs\nrainfall mm/h\nhumidity %\ntemperature C\nwater level m', fc=PALE, fs=5.3)
    box(ax, 23, 36, 19, 8, 'Range clipping\n(training bounds)', fs=5.3); box(ax, 46, 36, 21, 8, 'Random Forest\n100 trees, depth 6\n3 weather inputs', fc=OK, fs=5.2)
    box(ax, 23, 22, 19, 8, 'Gauge rule\nwater level >= 2.5 / 3.8 / 5.5 m', fc=WARN, fs=5.0)
    box(ax, 71, 29, 27, 15, 'Risk class\nLOW / MODERATE / HIGH / CRITICAL\n(higher of model band\nand gauge band)', fc=WARN, fs=5.2)
    arrow(ax, (19, 40), (23, 40)); arrow(ax, (42, 40), (46, 40)); arrow(ax, (67, 40), (71, 38)); arrow(ax, (19, 34), (23, 26)); arrow(ax, (42, 26), (71, 31))
    box(ax, 46, 8, 52, 12, 'Scenario projections (heuristic, not a forecast model)\nP(+t) = clip( P + rainfall/100 x 0.15 x k_t ),  k = 0.5, 0.9, 1.3 for +30, +45, +60 min', fc=LIGHT, fs=5.2)
    arrow(ax, (56, 36), (56, 20), 'probability P', fs=4.8, off=(4, 0))
    box(ax, 2, 8, 40, 12, 'Provenance labels: inputs SIMULATED,\ntraining data HISTORICAL; no live feed', fc='white', ec=GREY, ls='--', fs=5.0)
    save(fig, 'f_mlpipe')

def f_vision():
    H = 40; fig, ax = canvas(H); title(ax, H, 'Flood photo analysis (ONNX Runtime, CPU)')
    box(ax, 2, 14, 16, 14, 'Uploaded photo\ntype, size, pixel\nlimits; EXIF read;\nstored privately', fc=PALE, fs=5.0)
    box(ax, 24, 22, 24, 11, 'CLIP ViT-B/32 (zero-shot)\n8 flood vs 10 normal prompts\nflood if probability >= 0.5', fc=OK, fs=5.0)
    box(ax, 24, 8, 24, 11, 'SegFormer-B0 (ADE20K)\nwater coverage; people,\nvehicles, boats in water', fc=OK, fs=5.0)
    box(ax, 54, 14, 22, 14, 'Suggested severity\n(label PREDICTED;\ndepth entered by\nthe reporter)', fc=WARN, fs=5.0)
    box(ax, 82, 14, 16, 14, 'Operator confirms\nduring verification', fc=PALE, fs=5.0)
    arrow(ax, (18, 23), (24, 27)); arrow(ax, (18, 19), (24, 14)); arrow(ax, (48, 27), (54, 23)); arrow(ax, (48, 14), (54, 19)); arrow(ax, (76, 21), (82, 21))
    save(fig, 'f_vision')

def f_deploy():
    H = 44; fig, ax = canvas(H); title(ax, H, 'Local deployment view (development and Windows laptop)')
    box(ax, 2, 6, 30, 30, '', fc='#f7fafc', ec=GREY, ls='--'); ax.text(4, 34, 'Browser', fontsize=6.2, fontweight='bold', color=TEAL, va='center'); box(ax, 5, 20, 24, 10, 'React SPA (Vite dev server\nor static build)', fc=PALE, fs=5.2); box(ax, 5, 9, 24, 8, 'Memory: access token\nCookie: refresh (HttpOnly)', fs=4.9)
    box(ax, 36, 6, 30, 30, '', fc='#f7fafc', ec=GREY, ls='--'); ax.text(38, 34, 'Application host (one machine)', fontsize=6.2, fontweight='bold', color=TEAL, va='center'); box(ax, 39, 20, 24, 10, 'Uvicorn + FastAPI\n(127.0.0.1:8000)', fc=PALE, fs=5.2); box(ax, 39, 9, 24, 8, 'SQLite, uploads/,\nbackups/, model files', fs=4.9)
    box(ax, 70, 6, 28, 30, '', fc='white', ec=GREY, ls='--'); ax.text(72, 34, 'Optional, outside the host', fontsize=6.2, fontweight='bold', color=GREY, va='center'); box(ax, 73, 22, 22, 8, 'Map tile providers', fs=5.0, fc='white'); box(ax, 73, 12, 22, 8, 'SMTP / Ollama (unverified)', fs=4.8, fc='white')
    arrow(ax, (32, 25), (36, 25), 'HTTP / JSON', fs=4.8, off=(0, 2.2)); arrow(ax, (66, 25), (70, 26), '', ls='--', color=GREY)
    save(fig, 'f_deploy')


def f_dfd1():
    H = 84; fig, ax = canvas(H); title(ax, H, 'Detailed data flow diagram (DFD level 1)')
    P = {1: (17, 68, '1.0 Authentication\nand session  [D1]'), 2: (50, 68, '2.0 Incident intake\nand evidence  [D2]'), 3: (83, 68, '3.0 Verification and\nlifecycle  [D2, D6]'),
         4: (17, 44, '4.0 Flood risk and\nscenario outlook  [D7]'), 5: (50, 44, '5.0 Triage and commander\napproval  [D2, D3, D5]'), 6: (83, 44, '6.0 Dispatch and\nrescue records  [D3]'),
         7: (17, 20, '7.0 Alerts (CAP 1.2)\nand notifications  [D4]'), 8: (50, 20, '8.0 Volunteers, squads,\nfacilities  [D3, D5]'), 9: (83, 20, '9.0 Audit and\ndiagnostics  [D6]')}
    for k, (x, y, t) in P.items():
        ax.add_patch(Ellipse((x, y), 29, 14, fc=PALE, ec=TEAL, lw=0.9, zorder=2)); ax.text(x, y, t, ha='center', va='center', fontsize=5.1, zorder=3, linespacing=1.2)
    A = lambda a, b, l='', **k: arrow(ax, a, b, l, fs=4.6, **k)
    A((31.5, 68), (35.5, 68), 'user', off=(0, 2.4)); A((64.5, 68), (68.5, 68), 'REPORTED', off=(0, 2.4))
    A((76, 61.4), (57, 50.4), 'VERIFIED', off=(4, 2)); A((31.5, 44), (35.5, 44), 'risk class', off=(0, 2.4)); A((64.5, 44), (68.5, 44), 'approved', off=(0, 2.4))
    A((17, 37), (17, 27), 'CRITICAL outlook'  , off=(-1, 0)); A((50, 37), (50, 27), 'squad, shelter', off=(0, 0)); A((83, 37), (83, 27), 'audit events', off=(0, 0))
    A((31.5, 20), (35.5, 20), 'alerts', off=(0, 2.4))
    stores = ['D1 users, sessions, MFA, invitations', 'D2 incidents, media, beacons', 'D3 rescue teams, rescue records', 'D4 alerts, notification outbox', 'D5 facilities, volunteers', 'D6 audit log', 'D7 datasets, flood model files']
    ax.add_patch(Rectangle((4, 0.5), 92, 11.8, fc='white', ec=GREY, lw=0.8, ls='--'))
    for i, t in enumerate(stores):
        ax.text(6 + (i % 2) * 46, 10.6 - (i // 2) * 2.7, t, fontsize=4.8, va='center')
    save(fig, 'f_dfd1')

def f_state():
    H = 62; fig, ax = canvas(H); title(ax, H, 'Incident lifecycle (state transition diagram)')
    w, h = 16, 8
    top = ['REPORTED', 'UNDER_VERIFICATION', 'VERIFIED', 'QUEUED', 'TRIAGE_IN_PROGRESS']; mid = ['PENDING_APPROVAL', 'DISPATCHED', 'IN_TRANSIT', 'ON_SCENE', 'RESOLVED']
    X = [3 + i * 19.5 for i in range(5)]; S = {}
    for k, x in zip(top, X): S[k] = (x, 46)
    for k, x in zip(mid, X[::-1]): S[k] = (x, 26)
    S['REJECTED'] = (S['PENDING_APPROVAL'][0], 6)
    for k, (x, y) in S.items():
        fc = OK if k == 'RESOLVED' else (WARN if k == 'PENDING_APPROVAL' else (LIGHT if k == 'REJECTED' else PALE)); box(ax, x, y, w, h, k.replace('_', ' '), fc=fc, fs=5.0, bold=(k == 'PENDING_APPROVAL'))
    r = lambda k: (S[k][0] + w, S[k][1] + h / 2); l = lambda k: (S[k][0], S[k][1] + h / 2); t = lambda k: (S[k][0] + w / 2, S[k][1] + h); b = lambda k: (S[k][0] + w / 2, S[k][1])
    for a, c in zip(top[:-1], top[1:]): arrow(ax, r(a), l(c))
    arrow(ax, b('TRIAGE_IN_PROGRESS'), t('PENDING_APPROVAL'), '5+ victims or\nHIGH / CRITICAL', off=(-13, 0), fs=4.8)
    arrow(ax, l('PENDING_APPROVAL'), r('DISPATCHED'), 'commander\napproves', off=(0, 3.6), fs=4.8)
    for a, c in zip(mid[1:-1], mid[2:]): arrow(ax, l(a), r(c))
    arrow(ax, b('PENDING_APPROVAL'), t('REJECTED'), 'declined', off=(6, 0), color=RED, fs=4.8)
    box(ax, 3, 3, 66, 16, 'Below the gate (fewer than 5 victims and LOW / MODERATE): the operator confirms and\nTRIAGE IN PROGRESS goes straight to DISPATCHED.\nSide branches: DUPLICATE and REJECTED: from REPORTED / UNDER VERIFICATION (invalid or duplicate report)\nCANCELLED: from most states before ON SCENE\nREJECTED can return to QUEUED or end as CANCELLED', fc='white', ec=GREY, ls='--', fs=4.8, ha='left')
    ax.add_patch(Circle((3, 58), 0.9, fc=NAVY, ec=NAVY)); arrow(ax, (3.8, 57.6), (8, 54.6), '')
    save(fig, 'f_state')

def f_er():
    H = 118; fig, ax = canvas(H); title(ax, H, 'Entity relationship overview of the 22 database tables')
    groups = [('Identity and access', 2, 70, 96, 44, 4, [('users', 'id, username, role, agency_id,\nteam_id, token_version'), ('auth_sessions', 'user_id, assurance,\nexpires_at, revoked_at'), ('refresh_tokens', 'session_id, token_hash,\nused_at'), ('mfa_credentials', 'user_id, secret_enc\n(AES-GCM), status'), ('mfa_recovery_codes', 'user_id, code_hash,\nused_at'), ('auth_challenges', 'user_id, purpose,\nexpires_at'), ('one_time_tokens', 'user_id, kind, hash,\nexpires_at'), ('invitations', 'role, agency_id,\ntoken_hash, expires_at'), ('agencies', 'name, agency_type,\nregion'), ('rate_limit_events', 'bucket, key, at'), ('notification_outbox', 'kind, recipient,\nstatus')]),
              ('Incidents and evidence', 2, 38, 96, 30, 4, [('incidents', 'status, severity, people,\nlat/lon, public_ref'), ('media_assets', 'incident_id, sha256,\nprivacy'), ('beacons', 'hotspot, lat/lon,\nbattery'), ('supervisor_tasks', 'incident_id, approval\nflag, approved_by'), ('rescue_records', 'incident_id, team_id,\noutcomes')]),
              ('Resources, governance and data', 2, 2, 96, 34, 4, [('rescue_teams', 'callsign, status,\nvehicle, agency_id'), ('volunteers', 'skills, is_verified,\nstatus'), ('facilities', 'type, capacity,\noccupancy'), ('alerts', 'severity, radius_km,\nescalation_level'), ('audit_logs', 'actor, role, action,\ntarget'), ('dataset_registry', 'name, records_count,\ncoverage')])]
    for name, x, y, w, h, cols, tabs in groups:
        box(ax, x, y, w, h, '', fc='#f7fafc', ec=GREY, ls='--'); ax.text(x + 1.5, y + h - 2.4, name, fontsize=6.2, fontweight='bold', color=TEAL, va='center')
        bw = (w - 3 - 1.5 * (cols - 1)) / cols; bh = 10.5
        for i, (tn, d) in enumerate(tabs):
            cx = x + 1.5 + (i % cols) * (bw + 1.5); cy = y + h - 6.5 - bh - (i // cols) * (bh + 1.6)
            box(ax, cx, cy, bw, bh, '', fc='white', r=0.6); ax.text(cx + 0.8, cy + bh - 1.8, tn, fontsize=5.0, fontweight='bold', color=NAVY, va='center'); ax.text(cx + 0.8, cy + 3.6, d, fontsize=4.0, va='center', color='#333', linespacing=1.15)
    save(fig, 'f_er')

def f_class():
    H = 100; fig, ax = canvas(H); title(ax, H, 'UML class diagram of the core domain entities')
    R = {}
    def cls(key, x, ytop, w, name, attrs, ops, fc=LIGHT):
        h = 5.0 + 2.5 * (len(attrs) + len(ops)) + 1.6; y = ytop - h
        ax.add_patch(Rectangle((x, y), w, h, fc='white', ec=NAVY, lw=0.9, zorder=2)); ax.add_patch(Rectangle((x, y + h - 5.0), w, 5.0, fc=fc, ec=NAVY, lw=0.9, zorder=2))
        ax.text(x + w / 2, y + h - 2.5, name, ha='center', va='center', fontsize=5.8, fontweight='bold', zorder=3)
        sep = y + h - 5.0 - 2.5 * len(attrs) - 0.8; ax.plot([x, x + w], [sep, sep], color=NAVY, lw=0.6, zorder=3)
        for i, a in enumerate(attrs + ops): ax.text(x + 0.9, y + h - 7.3 - i * 2.5 - (0.8 if i >= len(attrs) else 0), a, fontsize=4.5, va='center', zorder=3, family='monospace')
        R[key] = (x, y, w, h); return y
    gap = 5
    y = 95
    y = cls('ag', 3, y, 28, 'Agency', ['id, name, agency_type', 'region, is_active'], ['invite(role)'], PALE) - gap
    y = cls('us', 3, y, 28, 'User', ['id, username, role', 'agency_id, team_id', 'mfa_status, token_version'], ['sign_in()', 'enrol_mfa()', 'permissions()'], PALE) - gap
    y = cls('se', 3, y, 28, 'AuthSession', ['user_id, assurance', 'expires_at, revoked_at'], ['rotate_refresh()', 'revoke()'], PALE) - gap
    y = cls('au', 3, y, 28, 'AuditLog', ['actor, role, action', 'target_id, created_at'], ['record()']) - gap
    y = 95
    y = cls('in', 36, y, 30, 'Incident', ['id, public_ref, status', 'severity, people_affected', 'lat, lon, data_label', 'assigned_team_id'], ['transition(to)', 'requires_approval()', 'effective_risk()'], WARN) - gap
    y = cls('me', 36, y, 30, 'MediaAsset', ['incident_id, sha256', 'content_type, privacy'], ['analyse_photo()']) - gap
    y = cls('st', 36, y, 30, 'SupervisorTask', ['incident_id', 'requires_human_approval', 'approved_by, status'], ['recommend()', 'decide()'], WARN) - gap
    y = cls('rr', 36, y, 30, 'RescueRecord', ['incident_id, team_id', 'people_rescued, notes'], ['export_csv()']) - gap
    y = 95
    y = cls('rt', 71, y, 27, 'RescueTeam', ['callsign, status', 'vehicle_type, agency_id'], ['deploy()', 'release()']) - gap
    y = cls('vo', 71, y, 27, 'Volunteer', ['skills, is_verified', 'status, area'], ['verify()']) - gap
    y = cls('fa', 71, y, 27, 'Facility', ['type, capacity', 'current_occupancy'], ['free_places()']) - gap
    y = cls('al', 71, y, 27, 'Alert', ['severity, area, radius_km', 'status, escalation_level'], ['to_cap_xml()', 'escalate()']) - gap
    P = lambda k, side, f=0.5: {'r': (R[k][0] + R[k][2], R[k][1] + R[k][3] * f), 'l': (R[k][0], R[k][1] + R[k][3] * f), 't': (R[k][0] + R[k][2] * f, R[k][1] + R[k][3]), 'b': (R[k][0] + R[k][2] * f, R[k][1])}[side]
    L = lambda a, b, lab='', **k: arrow(ax, a, b, lab, fs=4.4, style='-', lw=0.8, color=GREY, **k)
    L(P('ag', 'b', .5), P('us', 't', .5), '1..*', off=(3, 0)); L(P('us', 'b', .5), P('se', 't', .5), '1..*', off=(3, 0)); L(P('us', 'r', .6), P('in', 'l', .85), 'reports', off=(0, 1.8))
    L(P('in', 'b', .5), P('me', 't', .5), '1..*', off=(3, 0)); L(P('me', 'b', .5), P('st', 't', .5), '', off=(3, 0)); L(P('st', 'b', .5), P('rr', 't', .5), '')
    L(P('in', 'r', .8), P('rt', 'l', .5), 'assigned team', off=(0, 1.8)); L(P('in', 'r', .45), P('vo', 'l', .5), 'volunteer', off=(0, 1.8))
    L(P('st', 'r', .5), P('fa', 'l', .5), 'suggests', off=(0, 1.8))
    save(fig, 'f_class')


if __name__ == '__main__':
    for f in [f_arch, f_workspace, f_dfd0, f_dfd1, f_usecase, f_state, f_seq_incident, f_seq_auth, f_activity, f_er, f_class, f_perm, f_basemap, f_mlpipe, f_vision, f_deploy]: f()
    print('ok')
