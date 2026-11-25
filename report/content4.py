import ast
from rb import *
R = '/home/user/rescuenet-x/'

def src(path, name, maxlines=40):
    t = open(R + path).read(); tree = ast.parse(t)
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            s = ast.get_source_segment(t, n); L = s.split('\n')
            if len(L) > maxlines: L = L[:maxlines] + ['    ...']
            return '\n'.join(L)
    raise KeyError(name)

def build_ch7(b):
    b.chapter(7, 'Implementation')
    b.p('This chapter describes how the platform is implemented as back-end modules, a REST API and front-end views, and shows excerpts of the real source code for the most important logic.')
    b.h2('7.1 Module Overview')
    mods = [['1', 'Authentication and sessions', 'auth routes, sessions.py, security.py', 'Sign-in, refresh rotation, CSRF, logout, session revocation'],
            ['2', 'Multi-factor authentication', 'mfa.py, mfa_crypto.py, mfa routes', 'TOTP, recovery codes, challenges, AES-GCM secrets, step-up'],
            ['3', 'Permission matrix and workspace', 'permissions.py, navigation.py, deps.py', 'Role to permission, navigation, capabilities, guards'],
            ['4', 'Invitations, agencies, provisioning', 'invitations, agencies, provisioning.py', 'Privileged account creation, bootstrap and demo scripts'],
            ['5', 'Contact verification and recovery', 'auth_state.py, notifications.py', 'Verification and recovery codes, notification outbox'],
            ['6', 'Rate limiting', 'rate_limit.py', 'Database-backed limits per endpoint group'],
            ['7', 'Public reporting and tracking', 'public routes, public_refs.py', 'Guest and citizen reports, reference and tracking code'],
            ['8', 'Evidence media', 'media.py, media routes', 'Validation, private storage, authenticated retrieval'],
            ['9', 'Incident lifecycle', 'incident_lifecycle.py, incidents routes', 'States, transitions, effective risk, approval rule'],
            ['10', 'Verification', 'verification.py', 'Verify, reject, mark duplicate; verifier recorded'],
            ['11', 'Dispatch and team selection', 'dispatch.py, team_selection.py', 'Atomic dispatch, one team per incident'],
            ['12', 'Supervisor and triage', 'agents routes, ollama_service.py', 'Nearest squad and shelter, gate, optional LLM fallback'],
            ['13', 'Flood model and forecast', 'flood_model.py, flood routes', 'Training, evaluation record, prediction, scenarios'],
            ['14', 'Photo analysis', 'vision_service.py, vision routes', 'CLIP and SegFormer through ONNX Runtime'],
            ['15', 'Catchments and gauges', 'geo_service.py, datasets routes', 'Shapefile to GeoJSON, gauge metadata'],
            ['16', 'Trilateration', 'trilateration.py', 'RSSI path loss and least-squares position'],
            ['17', 'Alerting', 'alerting.py, alerts routes', 'Duplicates, escalation, CAP 1.2 XML'],
            ['18', 'Facilities, squads, volunteers', 'facilities, teams, volunteers routes', 'Capacity, availability, verification'],
            ['19', 'Rescue records and audit', 'records routes, audit.py', 'Outcomes with CSV export; audit entries'],
            ['20', 'Diagnostics and start-up checks', 'diagnostics, health, startup_checks.py', 'Live checks, production configuration validation']]
    b.tbl('Back-End Modules', ['No.', 'Module', 'Main files', 'Responsibility'], mods, widths=[0.7, 2.8, 3.3, 4.4], size=8.8)
    b.h2('7.2 Module Descriptions')
    b.p('**Authentication and sessions.** The sign-in endpoint accepts an email or username and a password and a portal hint (automatic by default, so the portal is derived from the verified account). It applies the rate limit, checks the PBKDF2 hash with lock-out counters, and either returns a single-use MFA challenge or creates a server-side session. The access token carries the session identifier and a token version, so changing a password or role invalidates earlier tokens. The refresh endpoint rotates a single-use token and checks the Origin and a CSRF double-submit value.')
    b.p('**MFA.** Enrolment needs the current password, shows a QR code and setup key once, requires a confirming code and then issues ten recovery codes shown once. Verification refuses a replayed TOTP step, recovery codes are single-use, and password recovery never removes MFA. Sensitive actions, such as approving a dispatch, require a recent second factor.')
    b.p('**Permission matrix and workspaces.** `permissions.py` defines 42 permissions and the permission set of each role; `deps.py` turns them into route guards; `navigation.py` derives, from the same permissions and the authentication state, the experience, capabilities, navigation and landing page returned to the browser. Activation steps (change password, verify contact, enrol MFA) are part of the answer, so an unfinished account sees only the next step.')
    b.p('**Incident lifecycle, verification and dispatch.** The service holds the table of states and transitions and the approval rule. The transition function refuses unknown or illegal moves with 422 or 409, checks that only a role with the dispatch permission may dispatch, and lets an incident that needs approval reach DISPATCHED only through the approval route. The dispatch service checks its preconditions inside one transaction, so a squad cannot be given to two incidents.')
    b.p('**Supervisor and triage.** For an incident, the service ranks AVAILABLE squads and shelters with enough free places by Haversine distance, builds a task with findings and recommendations, and sets the approval flag by the gate rule. An optional local language model can phrase the advice; because none is reachable in the test environment, the rule-based triage is the verified path, and the interface states which one produced the advice.')
    b.p('**Flood model and forecast.** On first use the service trains or loads the Random Forest, evaluates it (hold-out, cross-validation, chronological split and a four-test honesty suite) and stores the evaluation record. The prediction function applies the model, the gauge rule and the scenario formula. The dashboard shows an example scenario that is labelled as such.')
    b.p('**Photo analysis.** The vision service loads two ONNX models lazily, decodes the image safely, computes the CLIP flood probability and the SegFormer water coverage and the objects touching water, and returns a suggested severity with the label PREDICTED. It runs in about 190 ms per photo on CPU.')
    b.p('**Alerting.** The alert service finds duplicates, escalates overdue alerts, and builds CAP 1.2 XML with an alert, an info block and an area circle. Acknowledgement is recorded with the acknowledging user. The notification outbox records messages such as verification codes; in development the outbox is a file or screen, and a server without an email provider reports email as unavailable.')
    b.p('**Datasets and catchments.** The geo service reads the gauge metadata for Karnataka and converts shapefile polygons to GeoJSON. The datasets route reports each dataset with its provenance and, for the flood data, the leakage note, so the Data & Models view can explain what the model was trained on.')
    b.h2('7.3 REST API')
    b.p('The back end exposes 104 HTTP operations under /api, grouped by domain (Table 7.2). All write endpoints validate input with Pydantic, check the caller’s role, and audit consequential actions. Responses carry the data label of each record so the interface can mark simulated data.')
    b.tbl('Principal API Groups', ['Group', 'Representative operations', 'Access'], [
        ['auth', 'login, mfa verify, refresh, logout, me, register, password recovery, contact verification, sessions', 'Public for sign-in and registration; authenticated for the rest'],
        ['mfa', 'enrol, confirm, regenerate recovery codes, disable', 'Authenticated, password and recent MFA'],
        ['invitations, agencies', 'create, list, revoke, accept invitation; create and update agencies', 'Administrator (agencies) and invited person (accept)'],
        ['public', 'create report, track report, public workspace', 'Guest and above, rate limited'],
        ['incidents', 'list, read, verify, transition, assign, downgrade, summary', 'Operator, commander, officer by permission'],
        ['agents', 'supervisor tasks: request, list, approve, decline', 'Operator (request), commander (decide)'],
        ['alerts', 'create, list, acknowledge, resolve, CAP XML', 'Public read; operator or commander publish'],
        ['flood, datasets', 'forecast scenario, datasets and gauges, catchments GeoJSON', 'Public read for scenario; data permission for details'],
        ['teams, volunteers, facilities, records', 'squads, volunteer verification, capacity updates, outcome records, CSV', 'By permission'],
        ['vision, media', 'photo analysis, authenticated private media', 'Authenticated; anonymous gets 401'],
        ['diagnostics, health', 'live checks, system status', 'Developer or administrator; health is public']], widths=[2.3, 5.7, 3.3], size=9)
    b.h2('7.4 Front-End Implementation')
    b.p('The front end contains the public portal and operations console shells, the authentication screens and about twenty views. The shell is chosen by the server’s workspace answer. Routes are taken from that answer, so the browser address, the back and forward buttons and a page refresh all resolve against what the server offers. Table 7.3 lists the views.')
    b.tbl('Front-End Views', ['View', 'Purpose'], [
        ['Home, Emergency Alerts, Facilities and Shelters', 'Public flood watch, alerts and shelters with distance'],
        ['Flood Digital Twin', 'Map of catchments, gauges and assets; expandable "About this data" disclosure; gauge table'],
        ['Flood Forecasting', 'Scenario inputs, risk class, probability, trend chart of heuristic projections, factors; model details for staff only'],
        ['Report Emergency, My Reports', 'Reporting form with location picker and photo; own report list; tracking'],
        ['Overview', 'Four KPI cards, forecast card and map side by side, priority triage queue, alerts in force'],
        ['Rescue Operations, My Missions', 'Incident registry with filters and lifecycle actions; squads; assigned missions'],
        ['AI Supervisor', 'Triage tasks with findings, recommendations and the commander approval gate'],
        ['Volunteer Coordination, Rescue Records, Incident Reports', 'Volunteer verification, outcome records, intake with photo analysis'],
        ['Data & Models', 'Datasets, model evaluation and its limitations'],
        ['Admin Console, Agencies and Invitations, Audit Log, Settings, Diagnostics', 'Users, invitations, audit events, appearance, live checks'],
        ['My Account', 'Profile, password, MFA, sessions']], widths=[4.2, 7], size=9)
    b.p('**Map component.** One map component serves every page. It offers four visual presets (Classic, Tactical, Navigation and Flood Intelligence) that change marker style and labels but not the data, an independent light, dark or follow-theme appearance, marker clustering, local-first place search, a legend that lists only the layers currently drawn, and fullscreen and recentre controls. Its settings and legend are two small icons that open dismissible panels. The component recalculates its size when its container changes, so opening a navigation drawer never leaves a broken map.')
    b.p('**Theme system.** The application theme (Light, Dark or System default) is chosen from one icon menu in every header and sign-in screen, is remembered in the browser, follows the operating system when set to System, and synchronises across tabs. The map appearance is a separate setting, so a light application can contain a dark map and the reverse. Colours come from semantic design tokens, which keeps both themes consistent.')
    b.h2('7.5 Code Excerpts')
    b.p('The following excerpts are taken unchanged from the repository (long functions are shortened where marked). They show the rules that matter most for safety and security.')
    b.code('Approval rule and effective risk (incident_lifecycle.py)', src('backend/app/services/incident_lifecycle.py', 'requires_commander_approval') + '\n\n' + src('backend/app/services/incident_lifecycle.py', 'effective_risk'))
    b.code('Permission guard for every protected route (deps.py)', src('backend/app/api/deps.py', 'require_permission'))
    b.code('Dispatch preconditions inside one transaction (dispatch.py)', src('backend/app/services/dispatch.py', '_check_dispatchable', 26))
    b.code('Duplicate alert detection (alerting.py)', src('backend/app/services/alerting.py', 'find_duplicate'))
    b.code('Great-circle distance (ollama_service.py)', src('backend/app/services/ollama_service.py', 'haversine_km'))
    b.code('Log-distance path loss used by trilateration (trilateration.py)', src('backend/app/services/trilateration.py', 'rssi_to_distance_m'))
    b.code('Server-driven route resolution on the front end (auth/access.ts)', '''export function pathForPage(ws: Workspace | null, page: Page): string | null {
  for (const s of ws?.navigation.sections ?? []) for (const i of s.items) if (i.label === page) return i.path;
  return null;
}
export function pageForPath(ws: Workspace | null, path: string): Page | null {
  for (const s of ws?.navigation.sections ?? []) for (const i of s.items) if (i.path === path) return i.label as Page;
  return null;
}
export const can = (ws: Workspace | null, capability: string): boolean => Boolean(ws?.capabilities?.[capability]);''')

def build_ch8(b):
    b.chapter(8, 'System Testing')
    b.p('This chapter describes how the platform was verified and how the flood-risk classifier and the photo analysis were evaluated. Software test results (functionality and security) are kept apart from machine-learning metrics, because they answer different questions.')
    b.h2('8.1 Testing Strategy')
    b.p('Verification was organised in layers. **Unit and service tests** check the rules in isolation. **API tests** call the real FastAPI application against a throw-away database. **Authorisation tests** exercise every endpoint as every role. **Migration tests** upgrade, downgrade, back up and restore the database for each revision. **Front-end tests** check components, navigation helpers and regression conditions. **Scripted browser runs** drive the real application end to end on a fresh database and sweep every page. **Model evaluation** measures the classifier and the photo analysis on their datasets. Table 8.1 gives the headline results.')
    b.tbl('Summary of Test Execution', ['Suite', 'Result'], [
        ['Complete backend suite (throw-away database)', '782 passed, 1 skipped (live Ollama, none reachable)'],
        ['P0 dispatch safety (approval gate, atomic dispatch, team selection)', '66 passed'],
        ['Private media and public references', '53 passed'],
        ['Invitations, agencies, bootstrap and demo scripts, start-up validation', '69 passed'],
        ['Workspaces and navigation, endpoint authorisation matrix, migrations', '52 passed'],
        ['Front-end unit, component and regression tests (Vitest)', '61 passed'],
        ['Front-end production build', 'passes'],
        ['pip-audit and npm audit (production dependencies)', 'no known vulnerabilities at the time of the run'],
        ['Scripted browser verification on a fresh database', 'guest report and tracking, registration, all five staff roles, every console page per role, unauthorised navigation, session revocation, invitation with contact verification and mandatory MFA, private media, approval gate: passed']], widths=[6, 5.6], size=9.2)
    b.fig('fig/f_tests.png', 'Automated test results (counts of tests that passed)', 13.4)
    b.h2('8.2 Safety and Security Test Results')
    b.p('The most important tests concern the approval gate. They give the triage service a recommendation to dispatch an incident with seven victims and check that it still ends in PENDING APPROVAL; they check that an operator receives 403 when trying to approve; that an incident cannot be dispatched twice or to a busy squad; that editing the severity or the number of people cannot lower the effective risk; and that a downgrade needs a written authorisation by a commander or administrator. Because dispatch happens in one transaction, concurrent attempts leave consistent records.')
    b.tbl('Selected Security and Policy Tests', ['Area', 'What is verified'], [
        ['Permission matrix', 'Every one of 104 operations is called anonymously and as each of the seven roles and compared with a golden file; an endpoint without an expectation fails the suite.'],
        ['Sessions', 'Access tokens die with the session; refresh tokens rotate and are single-use; password, role or team change revokes sessions; idle and absolute timeouts apply.'],
        ['CSRF and cookies', 'Refresh needs the Origin and the double-submit value; cookies are HttpOnly and SameSite=Strict (Secure in production).'],
        ['MFA', 'TOTP drift window, replay refusal, single-use recovery codes, lock-outs, MFA not removable by password recovery, step-up for sensitive actions.'],
        ['Accounts', 'No self-registration of privileged roles; invitations single-use and expiring; demo accounts blocked in production; start-up validation of production settings.'],
        ['Private media', 'Anonymous requests for photographs get 401; guest tokens cannot read other reports; file type, size and pixel limits enforced.'],
        ['Rate limits', 'Sign-in, registration, verification, recovery and invitation endpoints are limited in the shared store.'],
        ['Migrations', 'Each of six revisions upgrades, downgrades and upgrades again; an automatic backup is taken and restore is verified.']], widths=[2.4, 9], size=9.2, bold_first=True)
    b.h2('8.3 Front-End and Browser Verification')
    b.p('Front-end tests cover the design components, navigation helpers, shells, the sign-in screen, the report receipt, route screens, the theme system (system detection, persistence, independence of the map appearance, cross-tab synchronisation, blocked storage), the base-map data and search, and the regression conditions found during the project. Two regressions are guarded by tests: a CSS class collision that once pulled the Overview map out of its grid cell, and a stacking defect that let map controls appear above the mobile navigation drawer.')
    b.p('Scripted Playwright runs sweep every page offered to each role at 360, 390, 768, 1024, 1440 and 1920 px in both themes, checking horizontal overflow, overlap of cards and map frames, map position, approximate text contrast and console errors. The final full run covered 552 page views across the guest, citizen, officer, commander, administrator and developer roles and reported no console errors. It found one real defect class, an overflow of the public header on narrow phones (4 px for guests and up to 32 px for signed-in citizens at 360 px), which was fixed and re-verified on 144 further page views. Earlier sweeps found and fixed horizontal overflow on four pages at phone widths and about twenty low-contrast texts in the light theme. All base-map tests were run with the tile hosts blocked to prove the offline fallback.')
    b.h2('8.4 Machine Learning Evaluation of the Flood-Risk Classifier')
    b.p('The served model was evaluated on a stratified hold-out set of 200 records and by stratified five-fold cross-validation over the 1,000 records (Table 8.3). The confusion matrix of the hold-out set (Figure 8.2, left) shows 153 true negatives, 41 true positives, 4 false positives and 2 false negatives. The 2 false negatives, flood conditions classified as normal, are the most important errors for an emergency system, which is one reason the platform combines the model with the gauge rule and verified reports instead of relying on the model alone.')
    b.tbl('Evaluation Metrics of the Served Random Forest (supplied dataset only)', ['Metric', 'Value', 'Note'], [
        ['Hold-out accuracy', '97.0 %', '800 training / 200 test records, stratified'],
        ['Precision / recall', '91.1 % / 95.3 %', 'Flood class, hold-out'],
        ['F1-score', '0.932', 'Hold-out'],
        ['ROC-AUC', '0.994', 'Hold-out'],
        ['5-fold cross-validation accuracy', '97.5 % (sd 0.6)', 'The figure shown in the confidence note; F1 0.943, recall 95.4 %'],
        ['Chronological hold-out accuracy', '97.5 %', 'Earlier rows train, later rows test'],
        ['Class balance', '784 non-flood, 216 flood', 'Flood prevalence 21.6 %']], widths=[3.6, 2.8, 5.2], size=9.2, bold_first=True)
    b.fig('fig/f_cm.png', 'Confusion matrices of the Random Forest (stratified and chronological hold-out)', 13.0)
    b.p('Four tests (Figure 8.3) show what the numbers mean. With all four inputs the score is 100 %, which is label leakage, because the label is "water level above 4.21 m". With weather inputs only, which is the served model, the score is 97.5 %; with a noisy gauge reading it stays 97.5 %. Predicting the next hour from the current hour reaches only 61.6 % accuracy with ROC-AUC 0.51, which is close to chance, because the rows are nearly independent hours. This is why the +30, +45 and +60 minute values in the application are a fixed heuristic and not model forecasts. Feature importance (Figure 8.4) is dominated by rainfall (88.2 %).')
    b.fig('fig/f_suite.png', 'Honest-evaluation suite: accuracy under four test conditions', 13.0)
    b.fig('fig/f_imp.png', 'Gini feature importance of the served model', 12.6)
    b.p('These figures describe one dataset whose collection method is not independently verified here. They are not evidence of performance on real future events, and no accuracy claim is made for a deployment. Water level influences the risk class through the gauge rule but is not a classifier input, and it does not affect the projections.')
    b.h2('8.5 Evaluation of the Photo Analysis')
    b.p('The flood decision of the photo analysis was scored on 809 flood photos from the project folder and 300 non-flood scenes from a public scene dataset (Figure 8.5). The prompts and threshold were fixed before scoring. The model found 99.3 % of the flood photos and raised false alarms on 7.3 % of the non-flood scenes (mostly water beside buildings, glaciers above water and some streets). Combined accuracy is 97.5 % with precision 97.3 % and specificity 92.7 %, but accuracy depends on the 809 to 300 mix, so detection rate and false-alarm rate are the fairer numbers. SegFormer alone detected 76.6 % of the floods and raised 24.3 % false alarms, which is why CLIP makes the decision and SegFormer adds measurements. SegFormer sometimes labels muddy flood water as earth, so water coverage can be low on a genuine flood photo, and water depth is not estimated. The non-flood photos are small and were not taken in Bengaluru, so real-world false-alarm rates may differ. All results are labelled PREDICTED and are confirmed by an operator.')
    b.fig('fig/f_vis_eval.png', 'Photo analysis: detection and false-alarm rates', 12.6)
    b.h2('8.6 What the Testing Does Not Show')
    b.bul(['No real emergency service, partner or deployment is involved; all operational data is simulated or public.',
           'Email delivery to a real mailbox and SMTP were not verified; SMS and push notifications do not exist.',
           'The optional language-model supervisor was not verified against a live Ollama server; the rule-based triage is the verified path.',
           'The Windows setup guide and the optional regional map-archive pipeline were written but not executed on a Windows machine, and the archive was tested only on a small synthetic fixture.',
           'There is no continuous browser test suite in the repository; browser verification is by scripted runs, and a full manual keyboard and screen-reader pass was not done.'])
