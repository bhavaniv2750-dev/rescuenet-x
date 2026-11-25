import json
from rb import *
from rb import _rf, _shade, _cell_margins
from docx.shared import Cm, Pt

PH = 'FFF2CC'  # placeholder highlight

def ph(b, para, text, size=12, bold=True):
    r = para.add_run(text); _rf(r, size, bold)
    rPr = r._element.get_or_add_rPr(); h = OxmlElement('w:highlight'); h.set(qn('w:val'), 'yellow'); rPr.append(h)

def front(b):
    d = b.d
    # ---- cover
    b.p('VISVESVARAYA TECHNOLOGICAL UNIVERSITY', 17, True, align='c', after=0, color='C0392B', ls=1.0)
    b.p('Jnana Sangama, Belagavi – 590014', 12, True, align='c', after=8, ls=1.0)
    p = d.add_paragraph(); p.alignment = 1; p.add_run().add_picture('fig/logo_vtu.png', width=Cm(3.1)); p.paragraph_format.space_after = Pt(8)
    b.p('PROJECT REPORT ON', 13, True, align='c', after=4, ls=1.0)
    b.p('“FLOOD DIGITAL TWIN AND RESCUENET X 2.0: AI-ASSISTED FLOOD RISK INTELLIGENCE AND EMERGENCY RESPONSE COORDINATION”', 14, True, align='c', after=12, ls=1.15)
    b.p('In partial fulfillment of the requirements for the award of the Degree of', 11.5, True, italic=True, align='c', after=8, ls=1.0)
    b.p('Bachelor Of Engineering', 15, True, align='c', after=2, color='C0392B', ls=1.0)
    b.p('In', 13, True, italic=True, align='c', after=2, ls=1.0)
    b.p('CSE-DATA SCIENCE', 14, True, align='c', after=2, color='3B7DBF', ls=1.0)
    b.p('By', 13, True, align='c', after=6, ls=1.0)
    for i in range(1, 5):
        para = d.add_paragraph(); para.alignment = 0; para.paragraph_format.left_indent = Cm(2.6); para.paragraph_format.space_after = Pt(1); para.paragraph_format.line_spacing = 1.0
        para.paragraph_format.tab_stops.add_tab_stop(Cm(9.6)); ph(b, para, f'[STUDENT NAME {i}]', 12); r = para.add_run('\t'); ph(b, para, '[USN]', 12)
    b.p('Under the guidance of', 12, align='c', after=2, before=8, ls=1.0)
    para = d.add_paragraph(); para.alignment = 1; para.paragraph_format.space_after = Pt(0); ph(b, para, '[GUIDE NAME, DESIGNATION]', 12)
    b.p('Dept. Of CSE-Data Science, ACSCE, Bangalore', 11, True, align='c', after=6, color='1E5631', ls=1.0)
    p = d.add_paragraph(); p.alignment = 1; p.add_run().add_picture('fig/logo_acs.png', width=Cm(2.7)); p.paragraph_format.space_after = Pt(4)
    b.p('DEPARTMENT OF CSE-DATA SCIENCE', 13, True, align='c', after=0, color='3B7DBF', ls=1.0)
    b.p('ACS COLLEGE OF ENGINEERING', 14, True, align='c', after=0, color='C0504D', ls=1.0)
    b.p('Bangalore -560074', 11, True, align='c', after=0, color='C0504D', ls=1.0)
    b.p('2025-2026', 11, True, align='c', after=0, ls=1.0)

    # ---- certificate
    b.pagebreak(); b.p('ACS COLLEGE OF ENGINEERING', 15, True, align='c', after=0, ls=1.0); b.p('Kambipura, Mysore Road, Bangalore – 560074', 11, True, align='c', after=8, ls=1.0)
    p = d.add_paragraph(); p.alignment = 1; p.add_run().add_picture('fig/logo_acs.png', width=Cm(2.6)); p.paragraph_format.space_after = Pt(6)
    b.p('DEPARTMENT OF CSE-DATA SCIENCE', 14, True, align='c', after=8, ls=1.0); b.p('CERTIFICATE', 15, True, align='c', after=10, ls=1.0)
    para = d.add_paragraph(); para.paragraph_format.line_spacing = 1.5
    b._runs(para, 'Certified that the project work entitled ', 12); b._runs(para, '“FLOOD DIGITAL TWIN AND RESCUENET X 2.0: AI-ASSISTED FLOOD RISK INTELLIGENCE AND EMERGENCY RESPONSE COORDINATION” ', 12, True)
    b._runs(para, 'was carried out by ', 12)
    for i in range(1, 5):
        ph(b, para, f'[Student Name {i}] ([USN])', 12); b._runs(para, ', ' if i < 4 else ', ', 12)
    b._runs(para, 'Bonafide students of ', 12); b._runs(para, 'ACS College Of Engineering ', 12, True); b._runs(para, 'in partial fulfillment for the award of ', 12); b._runs(para, 'Bachelor of Engineering in CSE-Data Science ', 12, True)
    b._runs(para, 'of the ', 12); b._runs(para, 'VISVESVARAYA TECHNOLOGICAL UNIVERSITY, BELAGAVI ', 12, True); b._runs(para, 'during the year 2025-2026. It is certified that all corrections/suggestions indicated for the Internal Assessment have been incorporated in the Report deposited in the departmental library. The project report has been approved as it satisfies the academic requirements in respect of Project work prescribed for the said Degree.', 12)
    b.p('', after=26)
    t = d.add_table(rows=2, cols=3); t.alignment = 1
    for i, (a, nm) in enumerate([('Signature of Guide', '[Guide name]'), ('Signature of HOD', 'Dr. B B S Kumar'), ('Signature of Principal', 'Dr. Shylaja B S')]):
        c = t.rows[0].cells[i]; c.text = ''; pp = c.paragraphs[0]; pp.alignment = 1; pp.paragraph_format.space_after = Pt(0); pp.paragraph_format.line_spacing = 1.0; b._runs(pp, a, 11.5, True)
        c = t.rows[1].cells[i]; c.text = ''; pp = c.paragraphs[0]; pp.alignment = 1; pp.paragraph_format.space_after = Pt(0); pp.paragraph_format.line_spacing = 1.0
        if i == 0: ph(b, pp, nm, 11, False)
        else: b._runs(pp, nm, 11.5)
    b.p('', after=14)
    t = d.add_table(rows=3, cols=3); t.alignment = 1
    for j, h in enumerate(['S N', 'Name of the Examiners', 'Signature with Date']):
        c = t.rows[0].cells[j]; c.text = ''; pp = c.paragraphs[0]; pp.alignment = 1; pp.paragraph_format.space_after = Pt(0); b._runs(pp, h, 11.5)
    for i in (1, 2):
        for j, v in enumerate([f'{i}.', '______________________________', '____________________']):
            c = t.rows[i].cells[j]; c.text = ''; pp = c.paragraphs[0]; pp.alignment = 1; pp.paragraph_format.space_after = Pt(4); b._runs(pp, v, 11.5)

    # ---- declaration
    b.pagebreak(); b.p('DECLARATION', 15, True, align='c', after=16, before=10, ls=1.0)
    para = d.add_paragraph(); para.paragraph_format.line_spacing = 1.6; para.paragraph_format.first_line_indent = Cm(1.2)
    b._runs(para, 'We ', 12)
    for i in range(1, 5): ph(b, para, f'[Student Name {i}] ([USN])', 12); b._runs(para, ', ' if i < 4 else ', ', 12)
    b._runs(para, 'hereby declare that this project report entitled ', 12); b._runs(para, '“FLOOD DIGITAL TWIN AND RESCUENET X 2.0: AI-ASSISTED FLOOD RISK INTELLIGENCE AND EMERGENCY RESPONSE COORDINATION” ', 12, True)
    b._runs(para, 'is a record of original work carried out by us under the guidance of ', 12); ph(b, para, '[Guide name]', 12)
    b._runs(para, ', Department of CSE-Data Science, ACS College of Engineering, Bangalore, in partial fulfillment of the requirements of the degree of Bachelor of Engineering in CSE-Data Science of Visvesvaraya Technological University, Belagavi. We further declare that we have not submitted this report either in part or in full to any other university for the award of any degree. In keeping with the ethical practice in reporting scientific information, due acknowledgments have been made wherever the findings of others have been cited.', 12)
    b.p('', after=40)
    for i in range(1, 5):
        para = d.add_paragraph(); para.paragraph_format.left_indent = Cm(5.6); para.paragraph_format.space_after = Pt(0); para.paragraph_format.line_spacing = 1.0; para.paragraph_format.tab_stops.add_tab_stop(Cm(11.6))
        ph(b, para, f'[STUDENT NAME {i}]', 11, False); para.add_run('\t'); ph(b, para, '[USN]', 11, False)
    b.p('', after=30); para = d.add_paragraph(); para.paragraph_format.space_after = Pt(0); b._runs(para, 'Place: Bangalore', 11.5); para = d.add_paragraph(); para.paragraph_format.space_after = Pt(0); b._runs(para, 'Date: ', 11.5); ph(b, para, '[date]', 11.5, False)

    # ---- acknowledgement
    b.pagebreak(); b.p('ACKNOWLEDGEMENT', 15, True, align='c', after=14, before=10, ls=1.0)
    ack = [('I take this opportunity to express my sincere gratitude and respect to the ', 'ACS College of Engineering', ', Bangalore for providing me an opportunity to carry out my project report.'),
           ('I express my deep regards to our honorable Chairman ', 'Dr. A C SHANMUGAM', ', for providing me an opportunity to fulfil my ambition in this prestigious institute.'),
           ('I would like to express my immense gratitude to ', 'Dr. SHYLAJA B S', ', Principal, ACS College of Engineering, Bangalore, for her timely help and inspiration during the tenure of the course.'),
           ('I express my sincere regards and thanks to ', 'Dr. B B S KUMAR', ', Associate Professor and HOD, CSE-Data Science, ACSCE, Bangalore for the encouragement and support throughout the work.')]
    for a, bd, c in ack:
        para = d.add_paragraph(); para.paragraph_format.line_spacing = 1.35; b._runs(para, a, 12); b._runs(para, bd, 12, True); b._runs(para, c, 12)
    para = d.add_paragraph(); para.paragraph_format.line_spacing = 1.35; b._runs(para, 'With a profound sense of gratitude, I acknowledge the guidance, support and encouragement of my guide ', 12); ph(b, para, '[Guide name, designation]', 12); b._runs(para, ', CSE-Data Science, ACSCE, Bangalore.', 12)
    para = d.add_paragraph(); para.paragraph_format.line_spacing = 1.35; b._runs(para, 'I hereby thank our Project Coordinator, ', 12); ph(b, para, '[Coordinator name]', 12); b._runs(para, ', Dept. of CSE-Data Science, for the encouragement and support.', 12)
    b.p('We also thank all the Teaching and Non-teaching staff of CSE-Data Science, who have helped us to complete the project in time.', 12)
    b.p('Project Team members:', 12, True, color='3B6A9C', align='c', after=4, before=8)
    for i in range(1, 5):
        para = d.add_paragraph(); para.paragraph_format.left_indent = Cm(5.6); para.paragraph_format.space_after = Pt(0); para.paragraph_format.line_spacing = 1.0; para.paragraph_format.tab_stops.add_tab_stop(Cm(11.6))
        ph(b, para, f'[STUDENT NAME {i}]', 11, False); para.add_run('\t'); ph(b, para, '[USN]', 11, False)

def abstract(b):
    b.p('ABSTRACT', 15, True, align='c', after=14, before=10, ls=1.0)
    for t in [
        'Urban flooding is one of the most frequent hazards in fast-growing cities such as Bengaluru, and the response to it is slowed by scattered information: river and rain data on one portal, citizen calls in another register, shelter capacity in a third, and warnings sent without any record of duplication or escalation. This report presents Flood Digital Twin and RescueNet X 2.0, a student-built decision-support prototype that brings flood-risk intelligence and emergency-response coordination into one web platform built on the principle Predict, Visualise, Respond.',
        'The platform has a FastAPI back end with a SQLite database, and a React and TypeScript front end with Leaflet maps. A geospatial view combines historical catchment boundaries and river-gauge reference levels with incidents, rescue squads and facilities, and keeps working offline through an automatic base-map fallback chain. A Random Forest classifier trained on rainfall, humidity and temperature estimates flood probability; the water level is applied separately as a transparent gauge rule, and the +30, +45 and +60 minute values are labelled heuristic scenario projections rather than forecasts. Citizens and volunteers report emergencies, optionally with a photo that is checked with CLIP and SegFormer models; operators verify incidents, a triage service proposes the nearest available squad and a shelter with enough capacity, and a deterministic rule holds every incident with five or more victims, or HIGH or CRITICAL severity, until a commander approves it.',
        'Security and honesty are design requirements. A central permission matrix covers seven roles, the server decides every user’s workspace and navigation, sessions are server-side with rotating refresh tokens, privileged accounts must use TOTP multi-factor authentication and are created only by invitation, evidence photographs are private, and consequential actions are audited. All seeded operational data is labelled SIMULATED, the catchment data HISTORICAL, and nothing is labelled LIVE. The complete backend suite of 782 tests and 61 front-end tests pass, and scripted browser sweeps over 552 page views at six screen widths in light and dark themes found no console errors. On the supplied dataset the classifier reaches 97.0 % hold-out accuracy (97.5 % in 5-fold cross-validation); the report explains why these figures describe one dataset only, and that no real deployment or live data feed exists.']:
        b.p(t, 12)

def build_ls(b):
    L = json.load(open('ls.json'))
    b.chapter(2, 'Literature Survey')
    b.p('This chapter reviews nine recent publications on flood prediction, digital twins, remote sensing and data-driven early warning. For each work, the authors, work carried out, methodology, merits and demerits are summarised, and a new **Remarks** paragraph states what the work means for this project: what it confirms, what it does not cover, and what Flood Digital Twin and RescueNet X 2.0 does differently. Section 2.10 compares the works with the proposed system and identifies the research gap.')
    remarks = {
     1: 'Eom et al. show that a learned flood model is most useful when its output reaches operators through a live twin view. The same idea is followed here, but at a much smaller scale: a 2D GIS view, a small Random Forest on three weather inputs, and no sensor network. Their need for long, dense sensor records is exactly what the present project lacks, because no live gauge feed is connected; this is why gauge readings are shown as unavailable and live data feeds appear under future work. Their work also stops before incident handling, which is the part this project adds.',
     2: 'LocalFLoodNet makes a strong point that upstream and neighbouring stations matter. The dataset available here comes from a single historical source with independent hourly rows, so a graph model cannot be justified, and no claim of that kind is made. The paper is useful as a target for later work once several linked gauges are available. Its game-engine twin also differs from the lightweight Leaflet view chosen here so that the console runs on an ordinary laptop.',
     3: 'The blockchain layer protects shared disaster data, a concern that this project meets in a lighter way: every consequential action is written to an audit log, commander approvals need a recent second factor, and evidence photographs are private. The reported 95.58 % test accuracy is also a reminder that mixed real and synthetic training data can overstate real-world results, which is why this report separates dataset-bound metrics from software test results and labels simulated records as SIMULATED.',
     4: 'The Shapley-based selection of models is an elegant answer to changing conditions, but it needs an ensemble and satellite SAR data that are outside the scope of a student prototype. The present system keeps one transparent model and explains it (feature importances, a leakage audit and a gauge rule). The paper is a reference for a future ensemble once independently verified data exist.',
     5: 'The near-perfect scores of this work on a limited dataset deserve caution, and the experience of this project supports that caution: the Random Forest here scores 100 % when the water level is included, only because the label is defined from the water level. After the leakage was found, the served model uses weather inputs only. The remark is therefore that very high accuracy should always be accompanied by a data audit, which this report provides in Chapter 8.',
     6: 'This is the closest work in spirit: open source, low cost and aimed at places with little ground data. Flood Digital Twin and RescueNet X 2.0 shares that spirit, but it does not run a hydrodynamic model; its projections are a fixed heuristic and are labelled as such. Coupling the platform with an open hydrodynamic model such as HydroPol2D or LISFLOOD-FP is the natural next step for the forecasting side.',
     7: 'Data assimilation shows how a twin can be corrected by new observations. The present twin has no observation stream to assimilate, so it is a visualisation of historical boundaries and reference levels rather than a self-updating model, and it says so on the page. The work is useful for the roadmap: assimilating gauge readings into the scenario outlook would be the first step towards a real twin.',
     8: 'The review recommends modular, AI-driven twins suited to resource-constrained regions. The modular router and service structure of this project, its offline base-map fallback and its explicit provenance labels follow that advice. The 40 % reduction in response time quoted by the review comes from the studies it covers; no such figure is claimed for this prototype, which has not been deployed.',
     9: 'Multi-year, global forecasting answers a different question from the one an emergency operations centre asks in the next hour. The paper is included because it shows the limits of pure prediction work and the moderate accuracy (75 to 77 % ROC AUC) obtained when only coarse data exist. For this project it supports the decision to treat model output as advisory input to a human decision and not as an automatic trigger.'}
    for p in L['papers']:
        n = p['n']
        b.h2(f'2.{n} Authors: {p["auth"]}')
        b.p(f'**Work Carried Out:** {p["work"]}', 12)
        b.p('**Methodology:**', 12, after=2, keep=True); b.bul(p['meth'])
        b.p('**Merits:**', 12, after=2, keep=True, before=2); b.bul(p['mer'])
        b.p('**Demerits:**', 12, after=2, keep=True, before=2); b.bul(p['dem'])
        b.p(f'**Remarks:** {remarks[n]}', 12, before=2)
    b.h2('2.10 Comparative Analysis and Research Gap')
    b.p('Table 2.1 compares the reviewed works with Flood Digital Twin and RescueNet X 2.0 on their core model, forecasting scope, support for off-grid SOS, triage logic and safety gate. The entries for the proposed system describe what is implemented and tested in this report, including its stated limits.')
    rows = L['tbl'][1:-1] + [['RescueNet X 2.0 (this work)', 'Random Forest (weather) + gauge rule; 2D GIS twin', 'Heuristic +30/+45/+60 min scenarios', 'Simulated LoRa SOS packets (no field trial)', 'Rule-based triage; optional LLM (unverified)', 'Deterministic commander gate (tested)']]
    b.tbl('Comparative Matrix of Existing Literature and RescueNet X 2.0', L['tbl'][0], rows, widths=[2.1, 2.5, 2.2, 2, 2.2, 2], size=9)
    b.p('The nine reviewed works advance flood prediction through deep learning, graph networks, neuro-fuzzy models, satellite data assimilation and digital twin visualisation, but they stop at prediction, mapping or early warning. None of them joins short-horizon local risk outlooks to a verified incident workflow, a human approval gate that software cannot bypass, role-based and multi-factor access control, tracked geo-targeted alerts, and honest labelling of simulated and historical data. This combination is the gap that Flood Digital Twin and RescueNet X 2.0 addresses. The work does not claim to match the predictive strength of the reviewed models: its contribution is the integrated, secure and explainable response workflow around a modest and openly documented risk model.')

def build_ch1(b):
    b.chapter(1, 'Introduction')
    b.p('Urban flooding is one of the most frequent and destructive natural hazards in fast-growing cities. Intense rainfall can overwhelm drains within minutes, flooding low-lying neighbourhoods, roads and lake margins before any official forecast has been issued. In Bengaluru, rapid construction over lake beds and stormwater channels has made heavy rain a recurring cause of waterlogged roads, stranded residents and disrupted services, as the floods of September 2022 showed. River basins elsewhere in Karnataka, such as the Shimsha and Gurupur basins, add the risk of riverine flooding.')
    b.p('Managing a flood emergency depends on fast and reliable information. An emergency operations centre (EOC) must follow rainfall and water levels, identify the areas likely to be affected, prioritise incoming calls and reports, decide which rescue squad to send, find shelters and hospitals with room, and warn the public, all within minutes. In practice this information sits in separate places: hydrological data on static portals, citizen reports in notebooks or chat groups, squad and shelter lists in spreadsheets. Every handover between these sources costs time, and mistakes made in haste, such as dispatching a team that is already busy, are hard to trace afterwards.')
    b.p('Flood Digital Twin and RescueNet X 2.0 is a student-built decision-support prototype that addresses these problems with one platform for flood-risk intelligence and emergency-response coordination, built around the principle **Predict, Visualise, Respond**. It joins a geospatial flood view and a flood-risk estimator to a verified incident workflow in which a human commander, not the software, authorises high-impact dispatches. Two design commitments run through the whole project: access to every function is decided by the server and tested, and every figure shown to a user says where it comes from, so that simulated or historical data is never mistaken for a live measurement.')
    b.h3('Significance of the Domain of Working')
    b.p('Flood preparedness and response form a field where small delays and small errors have large consequences. Software that organises information, shows risk on a map, keeps a trustworthy record of who decided what and when, and protects the people reporting emergencies can shorten the path from a report to a rescue. At the same time, a flood tool that overstates what it knows can do harm. This is why the work places as much weight on security, provenance and explainability as on prediction accuracy, and why it is described throughout as decision support and not as an automatic emergency system.')

    b.h2('1.1 Existing System')
    b.p('Existing flood monitoring and response arrangements use hydrological monitoring networks, GIS platforms, public warning channels and telephone-based emergency desks. Each is useful on its own, but together they leave the following gaps.')
    b.bul(['**Fragmented data silos:** river and rainfall data is published on portals that are separate from the dispatch desk, so coordinators have no single view of flood conditions and incident load.',
           '**Short-horizon outlooks are rare:** most public products give regional forecasts over a day or more, not a local outlook for the next hour.',
           '**Manual incident triage:** reports are recorded by hand, and severity, squad availability and shelter capacity are worked out from separate records.',
           '**Weak accountability:** it is often unclear who verified a report, who approved a dispatch and when, and shared logins make this worse.',
           '**Unverified reports and volunteers:** reports, photographs and volunteer sign-ups are rarely verified before resources are committed.',
           '**Untracked alerts:** warnings are broadcast without duplicate control or escalation of those that nobody acknowledges.',
           '**Dependence on connectivity:** map tiles and cloud services fail exactly when networks are stressed.'])
    b.h2('1.2 Proposed System')
    b.p('The proposed system links catchment geography with day-to-day emergency operations in one application with two workspaces, a public portal and a professional operations console. Its main components are listed below, and each is implemented and tested as described in Chapters 7 and 8.')
    b.num(['**Geospatial flood twin:** an interactive Leaflet map that shows IndoFloods catchment boundaries, river-gauge stations with their reference levels, incidents, rescue squads, hospitals, shelters and alert areas, with four selectable visual presets and light and dark appearance.',
           '**Flood-risk estimator:** a Random Forest classifier on rainfall, humidity and temperature, combined with a transparent gauge rule on the water level, and heuristic +30, +45 and +60 minute scenario projections that are labelled as such.',
           '**Incident framework:** guests and citizens report emergencies with an optional photo; evidence is private; a photo is analysed with CLIP and SegFormer models; an operator verifies the incident through a defined lifecycle.',
           '**Triage and commander approval gate:** a triage service proposes the nearest available squad and a shelter with enough room; a deterministic rule holds every incident with five or more victims or HIGH or CRITICAL severity until a commander approves it with a recent second factor.',
           '**Role-based access and server-driven workspaces:** a central permission matrix for seven roles; the server returns each user’s experience, capabilities and navigation, and the front end only renders them.',
           '**Account security:** server-side sessions with short-lived access tokens, rotating refresh cookies, TOTP multi-factor authentication for staff, invitations instead of handed-out passwords, rate limiting and an audit log.',
           '**Alerting:** geo-targeted alerts with CAP 1.2 XML export, duplicate suppression and time-based escalation of unacknowledged alerts.',
           '**Resources and records:** volunteer verification, rescue squads, facility capacity, mission records with CSV export.',
           '**Resilient mapping:** online base maps with an automatic fallback to a bundled offline map (Natural Earth and BBMP ward boundaries), and an optional regional vector-tile archive.',
           '**Honest provenance:** every record carries a SIMULATED, HISTORICAL or OBSERVED label, and nothing is presented as LIVE.'])
    b.h2('1.3 Motivation')
    b.p('River and urban floods in Karnataka repeatedly cause loss of life, displacement and economic damage. Reports from the 2022 Bengaluru floods describe stranded residents, blocked roads and difficulty in coordinating boats, tractors and shelters. A tool that gives an operations centre one shared picture, and keeps a clear record of each decision, addresses a real need.')
    b.p('A second motivation is trust. Emergency software handles personal data, locations and photographs of people in distress, and it directs scarce rescue resources. A prototype that is meant to be taken seriously must therefore show how it controls access, protects evidence, avoids silent automation and distinguishes real from simulated data. The project grew from an initial feature prototype into a hardened system as these requirements were identified and tested.')
    b.p('A third motivation is resilience and low cost. The platform runs on a single ordinary computer, needs no paid map or cloud service, and keeps a usable map when internet tiles cannot be reached, which suits a district control room as well as a student laboratory.')
    b.h2('1.4 Objectives of the Work')
    b.num(['Build a geospatial flood view that combines IndoFloods catchments and gauge stations with incidents, squads and facilities on an interactive map.',
           'Train and evaluate a flood-risk classifier on the supplied dataset with reproducible metrics, audit it for label leakage, and expose its result with honest caveats.',
           'Provide short-horizon scenario projections that are clearly labelled as heuristic.',
           'Implement an incident lifecycle that processes citizen reports with private photographic evidence, verification, triage and dispatch.',
           'Enforce a deterministic commander approval gate so that no high-impact dispatch happens without human authorisation.',
           'Protect the platform with a central permission matrix, server-driven navigation, strong session handling, multi-factor authentication and an audit log, and prove each control with automated tests.',
           'Offer alerts in a standard format (CAP 1.2) with duplicate control and escalation, and keep volunteer, squad and facility records.',
           'Keep the maps usable offline and the interface consistent in light and dark themes and on phone-sized screens, and verify this by scripted browser runs.'])
    b.h2('1.5 Key Features and Scope of the Work')
    b.p('Table 1.1 summarises the key features of the platform and the scope of each. The scope column is deliberately explicit about what the prototype does and does not do.')
    b.tbl('System Key Features and Operational Scope', ['Feature', 'Scope and engineering notes'], [
        ['Public flood portal', 'Flood watch, shelters with distance, gauge reference levels (no live reading), forecasting scenario tool, emergency numbers, reporting and tracking by reference and one-time code.'],
        ['Operations console', 'Overview, Rescue Operations, My Missions, AI Supervisor, Alerts, Digital Twin, Forecasting, Data & Models, Volunteers, Facilities, Records, Incident Reports, Admin, Agencies, Audit Log, Diagnostics, Settings.'],
        ['Flood-risk estimator', 'Random Forest (100 trees, depth 6) on rainfall, humidity and temperature; gauge rule on water level; hold-out accuracy 97.0 % on the supplied dataset only.'],
        ['Scenario projections', '+30, +45 and +60 minute values from a fixed runoff-surge formula applied to the model probability; heuristic, not validated forecasts.'],
        ['Incident lifecycle', 'Thirteen states from REPORTED to RESOLVED with duplicate, rejected and cancelled branches; every transition is checked by the server.'],
        ['Commander approval gate', 'Five or more victims, or HIGH or CRITICAL severity, requires a commander; the effective risk can be raised but not silently lowered.'],
        ['Photo evidence analysis', 'CLIP flood decision and SegFormer water coverage on CPU; label PREDICTED; water depth is entered by the reporter, not estimated.'],
        ['Access control', 'Seven roles, 42 permissions in one matrix; every one of 104 HTTP operations has a tested authorisation expectation.'],
        ['Authentication', 'PBKDF2-SHA256 passwords, 15-minute access token bound to a server session, rotating HttpOnly refresh cookie, TOTP MFA, recovery codes, invitations.'],
        ['Alerts', 'Geo-targeted alerts, CAP 1.2 XML export, duplicate suppression (1 km, 30 minutes), escalation after 10 / 20 / 60 minutes by severity.'],
        ['Offline-capable maps', 'Four online base maps (three CARTO styles and OpenStreetMap), automatic fallback to a 315 KB bundled map, optional regional PMTiles archive; the active source is always shown.'],
        ['Not in scope', 'Live gauge feeds, real SMS or push delivery, a field-tested LoRa network, hydrodynamic simulation, multi-agency tenant isolation, mobile applications.']],
        widths=[2.4, 6.6], size=9.5, bold_first=True)
    b.h2('1.6 Organization of the Project Report')
    for t in ['Chapter 1 introduces the problem, the existing and proposed systems, motivation, objectives and key features.',
              'Chapter 2 reviews nine related publications, adds remarks on each, and identifies the research gap.',
              'Chapter 3 specifies the system requirements and the hardware and software configuration.',
              'Chapter 4 explains the methodology: data, the risk model, scenario projections, geospatial methods, photo analysis, the approval gate, alert rules and the security mechanisms.',
              'Chapter 5 describes the tools and technologies used.',
              'Chapter 6 presents the system design with architecture, data flow, UML diagrams, database schema, security and map design, and algorithms.',
              'Chapter 7 describes the implementation of the modules, the REST API and the front-end views, with code excerpts.',
              'Chapter 8 presents the testing strategy and the verification, regression and model-evaluation results.',
              'Chapter 9 shows and discusses the results with screenshots of the running application.',
              'Chapter 10 concludes the report and lists limitations and future work.']: b.bul([t])
