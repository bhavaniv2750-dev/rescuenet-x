import os
from PIL import Image
from rb import *
R = '/home/user/rescuenet-x/'
os.makedirs('img', exist_ok=True)

def im(path, name):
    out = f'img/{name}.jpg'
    if not os.path.exists(out):
        i = Image.open(path).convert('RGB'); 
        if i.width > 1300: i = i.resize((1300, int(i.height * 1300 / i.width)), Image.LANCZOS)
        i.save(out, quality=84)
    return out
GA = R + 'docs/evidence/GA/'; UR = R + 'docs/evidence/UI_REGRESSION/'; RW = 'raw/'

def build_ch9(b):
    b.chapter(9, 'Results and Discussion')
    b.p('This chapter shows the running application. All screenshots are real captures of the application on a fresh database, taken with the final user interface. Records on the screens are seeded demonstration data and are labelled SIMULATED on the pages; accounts are development fixtures. Screenshots of the base map were taken with the online tile hosts blocked, so they show the bundled offline map (Natural Earth and BBMP ward boundaries), which is a map of wards, highways, rivers and lakes and not a street-level map. Sensitive values (the MFA secret, recovery codes, tracking codes) are blurred in the sanitised captures.')
    b.h2('9.1 Authentication and Account Security')
    b.p('Figure 9.1 shows the sign-in screen, which carries only the product name, and the registration screen, which offers citizen and volunteer accounts only: privileged roles cannot register. Staff must enrol multi-factor authentication before reaching the console; Figure 9.3 shows the setup QR code (sanitised) and Figure 9.4 the challenge shown at the next sign-in. The theme menu (a single icon at the top right of every header and sign-in screen) is visible in the sign-in screen.')
    b.fig2(im(UR + '02_login_dark_1440.png', 'login_dark'), 'Sign-in screen (dark theme)', im(GA + 'auth/01_registration_citizen_1440.png', 'reg'), 'Registration for citizens and volunteers')
    b.fig2(im(GA + 'auth/05_mfa_qr_sanitized_1440.png', 'mfaqr'), 'MFA enrolment with QR code (sanitised)', im(GA + 'auth/07_mfa_challenge_1440.png', 'mfach'), 'MFA challenge at sign-in')
    b.h2('9.2 Public Portal')
    b.p('The public portal (Figures 9.5 to 9.10) gives guests and citizens flood information without an account. The home page summarises alerts, gauges and shelters; the shelters page lists facilities with distance and capacity; the forecasting page lets a visitor set scenario inputs and see the risk class, the probability and the trend of the heuristic projections, labelled SIMULATED. The reporting form records category, severity, description, location and an optional photo; the receipt with the reference and one-time tracking code appears only after the server confirms the report, and the report can then be tracked.')
    b.fig2(im(RW + 'pub_home.png', 'pubhome'), 'Public home page', im(RW + 'pub_shelters.png', 'pubshel'), 'Facilities and shelters')
    b.fig2(im(RW + 'pub_forecast.png', 'pubfc'), 'Forecasting scenario tool (public)', im(GA + 'public/02_guest_reporting_form_filled_1440.png', 'repform'), 'Emergency report form')
    b.fig2(im(GA + 'public/03_guest_report_receipt_sanitized_1440.png', 'receipt'), 'Report receipt (reference and code blurred)', im(GA + 'public/04_guest_tracking_sanitized_1440.png', 'track'), 'Tracking a report')
    b.h2('9.3 Flood Digital Twin and Map Controls')
    b.p('The Flood Digital Twin page opens with the map as the focus. Its settings and legend are two small icons; the expandable "About this data" section carries the provenance disclosure. Figures 9.11 and 9.12 show the settings panel (visual preset, map appearance, basemap source and operational layers) and the legend, which lists only the layers that are drawn and distinguishes catchment boundaries, which are historical outlines, from flooded areas. Figures 9.13 to 9.16 show the four visual presets on the same Bengaluru view: Classic, Tactical, Navigation and Flood Intelligence. The same data is drawn in all four; only the marker style, labels and rings change.')
    b.fig2(im(UR + '04_public-flood-twin_settings-expanded_dark_1440.png', 'twinset'), 'Map settings panel', im(UR + '05_public-flood-twin_legend-expanded_dark_1440.png', 'twinleg'), 'Legend (only drawn layers)')
    b.fig2(im(RW + 'gis_classic.png', 'gisc'), 'Classic preset', im(RW + 'gis_tactical.png', 'gist'), 'Tactical preset')
    b.fig2(im(RW + 'gis_navigation.png', 'gisn'), 'Navigation preset', im(RW + 'gis_flood.png', 'gisf'), 'Flood Intelligence preset')
    b.h2('9.4 Themes and Independent Map Appearance')
    b.p('Figure 9.17 shows the single theme menu with the check mark beside the selected choice. The application theme and the map appearance are separate settings: Figure 9.18 shows a light application with a dark Tactical map and Figure 9.19 a dark application with a light Navigation map. Changing one does not reset the other, and the map viewport and overlays are kept when the theme changes.')
    b.fig2(im(UR + '12_theme-switcher-dropdown_light_1440.png', 'thmenu'), 'Theme menu (Light, Dark, System default)', im(UR + '13_light-app_dark-tactical-map_1440.png', 'lightdark'), 'Light application, dark Tactical map')
    b.fig(im(UR + '14_dark-app_light-navigation-map_1440.png', 'darklight'), 'Dark application, light Navigation map', 11.5)
    b.h2('9.5 Operations Console')
    b.p('The operations console (Figures 9.20 to 9.33) is used by staff after sign-in with MFA. The Overview shows four key indicators, the forecast card and the geospatial view side by side, and the priority triage queue. Rescue Operations lists squads and the incident registry with filters and lifecycle actions. The AI Supervisor view explains how triage runs, states that the language model is not reachable and that the rule-based fallback is used, and shows the evidence dossier; recommendations are advisory and a fixed rule always requires commander approval for gated incidents. The remaining pages cover alerts, volunteers, rescue records, incident reports, data and models, the audit log, administration, agencies and invitations, and diagnostics.')
    b.fig(im(UR + '07_overview_dark_1440.png', 'ovdark'), 'Operations console: Overview', 13.6)
    b.fig(im(UR + '09_rescue-operations_dark_1440.png', 'opsdark'), 'Rescue Operations registry', 13.6)
    b.fig(im(GA + 'console/commander_supervisor_pending_approval_1440.png', 'suppend'), 'Supervisor task pending commander approval', 13.6)
    b.fig2(im(RW + 'commander_ai-supervisor.png', 'sup'), 'AI Supervisor with rule-based fallback notice', im(GA + 'console/commander_dispatch_workflow_1440.png', 'disp'), 'Dispatch workflow after approval')
    b.fig2(im(RW + 'commander_emergency-alerts.png', 'alerts'), 'Emergency alerts (CAP export)', im(UR + '11_forecasting_dark_1440.png', 'fcdark'), 'Forecasting (staff view, model details collapsed)')
    b.fig2(im(RW + 'commander_data-models.png', 'datamod'), 'Data and Models', im(RW + 'commander_volunteer-coordination.png', 'vol'), 'Volunteer coordination')
    b.fig2(im(RW + 'commander_rescue-records.png', 'rec'), 'Rescue records', im(RW + 'commander_audit-log.png', 'audit'), 'Audit log')
    b.fig2(im(RW + 'admin_admin-console.png', 'admin'), 'Administrator console', im(RW + 'admin_agencies-invitations.png', 'agen'), 'Agencies and invitations')
    b.fig(im(RW + 'developer_diagnostics.png', 'diag'), 'Diagnostics (developer role)', 11.5)
    b.h2('9.6 Mobile Layout')
    b.p('On a phone the public header is compact: brand, emergency action, theme icon, sign-in icon and a menu button. The navigation opens as an overlay under the header, with a clear close control, and closes after navigation; the map is visible when it is closed and recalculates its size when the layout changes (Figures 9.34 and 9.35). The console Overview stacks its cards in one column on a phone (Figure 9.36).')
    b.fig2(im(UR + '15_mobile-gis_navigation-closed_390.png', 'mclosed'), 'Mobile map, navigation closed', im(UR + '16_mobile-gis_navigation-open_390.png', 'mopen'), 'Mobile navigation open', width=5.4)
    b.fig(im(UR + '18_mobile-overview_dark_390.png', 'mobov'), 'Console Overview on a phone (390 px)', 5.2)
    b.h2('9.7 Discussion')
    b.p('The results show that the platform meets its design goals at prototype level. The permission matrix, server-driven navigation, MFA and private media work together, and each is confirmed by tests. The approval gate cannot be bypassed by an operator, by an edit of the record or by a recommendation of the supervisor service. The map remains useful offline. The honest labelling is visible on every page: SIMULATED records, HISTORICAL boundaries, UNAVAILABLE live readings, and notices that the language model is not reachable.')
    b.p('The model results need care. A hold-out accuracy of 97.0 % on the supplied dataset says that, for this dataset, rainfall, humidity and temperature separate flood from normal hours well, and the feature importance shows that rainfall carries almost all of it. It does not say how well the model would do on a real river or a future storm, and the next-hour experiment shows that the data does not support forecasting. This is why the platform presents the estimate as decision support, applies the gauge rule separately, and labels the projections as heuristic.')
    b.h2('9.8 Evaluation Against the Objectives')
    b.tbl('Objectives and How They Are Met', ['Objective', 'Delivered by'], [
        ['1. Geospatial flood view', 'Leaflet twin with catchments, gauges, incidents, squads, facilities, alerts; four presets; legend; offline fallback (Chapters 6, 9)'],
        ['2. Evaluated flood-risk classifier', 'Random Forest with hold-out, cross-validation, chronological split, leakage audit and honest-evaluation suite (Section 8.4)'],
        ['3. Labelled short-horizon projections', 'Heuristic +30/+45/+60 minute scenarios, labelled SIMULATED (Sections 4.5, 9.2)'],
        ['4. Incident lifecycle with evidence', 'Thirteen-state lifecycle, private photos, photo analysis, tracking (Sections 4.7, 6.8)'],
        ['5. Deterministic approval gate', 'Rule outside any model; 66 P0 tests; operator receives 403 (Sections 4.7, 8.2)'],
        ['6. Access control and account security', 'Permission matrix, server-driven navigation, sessions, MFA, invitations, audit; 104 operations tested per role (Sections 4.9, 6.11)'],
        ['7. Alerts and records', 'CAP 1.2 export, duplicate suppression, escalation, volunteer and facility management, CSV records (Section 4.8)'],
        ['8. Usable offline and responsive interface', 'Fallback map chain, themes, six-width browser sweeps with no console errors (Sections 4.10, 8.3)']], widths=[3.4, 8.2], size=9.2)

def build_ch10(b):
    b.chapter(10, 'Conclusion and Future Work')
    b.h2('10.1 Conclusion')
    b.p('Flood Digital Twin and RescueNet X 2.0 brings flood-risk intelligence and emergency-response coordination into one platform. It joins a geospatial view of historical catchments and gauge reference levels to a flood-risk estimator, a verified incident lifecycle, a triage service and a commander approval gate that no software component can bypass. Around this core it provides role-based and server-driven access, multi-factor authentication for staff, invitation-based account creation, private evidence, tracked alerts in a standard format, an audit trail and a map that keeps working offline.')
    b.p('The work shows that an emergency-response prototype can be built to be explainable and safe by design. The complete backend suite of 782 tests, the 61 front-end tests and browser sweeps over 552 page views confirm the software behaviour. The risk model reaches 97.0 % hold-out accuracy on the supplied dataset, but an audit showed that this dataset allows label leakage and does not support forecasting, so the model uses weather inputs only, water level is a separate rule, and the next-hour values are labelled heuristic. The most important result of the project is not a high accuracy figure but a system that states clearly what it knows and what it does not.')
    b.h2('10.2 Limitations')
    b.bul(['**Data:** all operational data is simulated or public; the flood dataset comes from a single source whose collection method is not independently verified; no live gauge or rainfall feed is connected.',
           '**Forecasting:** the +30, +45 and +60 minute values are a heuristic formula and not a validated forecast model; no hydrodynamic simulation exists, so the digital twin is a GIS visualisation and not a validated twin.',
           '**Delivery:** alerts are shown inside the application and exported as CAP XML; SMS, push and phone delivery are not implemented, and email delivery to a real mailbox was not verified.',
           '**Beacons and supervisor:** the LoRa beacon registry is simulated and not field-tested; the optional language-model supervisor was not verified against a live runtime, so the rule-based triage is the verified path.',
           '**Architecture:** SQLite is single-node, agencies are metadata and not tenant isolation, and offline maps cover wards, highways and water but not streets or buildings.',
           '**Verification:** there is no real deployment; the Windows guide and the regional map pipeline were not run on Windows; there is no continuous browser test suite, and a full manual accessibility audit was not done.',
           '**Photo analysis:** it can raise false alarms on water beside buildings and under-measure muddy water, and it does not estimate depth.'])
    b.h2('10.3 Future Work')
    b.bul(['**Live data:** integrate gauge and rainfall feeds from the relevant agencies and show observed values with the OBSERVED label.',
           '**Forecasting:** replace the heuristic with a validated model trained on independent multi-station time series, and couple the twin to an open hydrodynamic model such as HydroPol2D or LISFLOOD-FP.',
           '**Alert delivery:** add a draft, review and approve workflow and real delivery channels with delivery tracking.',
           '**Offline-first field use:** a progressive web application for field teams that works without connectivity, and the regional vector-tile map archive built from OpenStreetMap data, with local street search.',
           '**Field-tested LoRa:** test the beacon gateway with compliant hardware at flood hotspots.',
           '**Stronger isolation and scale:** multi-agency data isolation and a server database for larger deployments.',
           '**Independent validation:** evaluation of triage recommendations and the interface by emergency-management professionals, and a formal accessibility audit.'])

REFS = ['H. Eom, Y. Kim, and J. Paik, “Design and Performance Verification of Deep Learning-Based River Flood Prediction System Design and Digital Twin-Based Its Application,” *Mathematics (MDPI)*, vol. 13, no. 11, Art. no. 1696, 2025.',
        'N. Shafiee Roudbari, S. R. Punekar, Z. Patterson, U. Eicker, and C. Poullis, “From Data to Action in Flood Forecasting Leveraging Graph Neural Networks and Digital Twin Visualization,” *Scientific Reports*, vol. 14, 2024.',
        'A. Manocha, M. Bhatia, and S. K. Sood, “Digital Twin-Assisted Fuzzy Logic-Inspired Intelligent Approach for Flood Prediction,” *IEEE Sensors Journal*, vol. 25, no. 15, 2025.',
        'Y. Djenouri et al., “Game-Theoretic Consensus Deep Learning for Adaptive Flood Prediction in Digital Twin Environments,” *IEEE J. Sel. Topics Appl. Earth Observations and Remote Sensing*, vol. 18, 2025.',
        'S.-J. Lim, K. Sakthidasan Sankaran, and A. Haldorai, “A Novel Framework for Detecting Flood Disaster: Spatio-Temporal Fusion and Digital Twin Approach,” *IEEE J. Sel. Topics Appl. Earth Observations and Remote Sensing*, 2025.',
        'L. M. C. Rápalo, M. N. Gomes Jr., and E. M. Mendiondo, “Developing an Open-Source Flood Forecasting System Adapted to Data-Scarce Regions: A Digital Twin Coupled with Hydrologic-Hydrodynamic Simulations,” *Journal of Hydrology*, 2024.',
        'T. H. Nguyen et al., “Towards Digital Twin in Flood Forecasting with Data Assimilation Satellite Earth Observations: A Proof-of-Concept in the Alzette Catchment,” arXiv preprint arXiv:2505.08553, 2025.',
        'M. Hlal et al., “Digital Twin Technology for Urban Flood Risk Management: A Systematic Review of Remote Sensing Applications and Early Warning Systems,” *Remote Sensing (MDPI)*, vol. 17, no. 17, Art. no. 3104, 2025.',
        'C. Zeng and D. Bertsimas, “Global Flood Prediction: A Multimodal Machine Learning Approach,” arXiv preprint arXiv:2301.12548, 2023.',
        'Central Water Commission, Hydrological Data Directorate, *Flood Forecasting Network in Karnataka River Basins*, Ministry of Jal Shakti, Government of India, 2023.',
        'L. Breiman, “Random Forests,” *Machine Learning*, vol. 45, no. 1, pp. 5–32, 2001.',
        'F. Pedregosa et al., “Scikit-learn: Machine Learning in Python,” *Journal of Machine Learning Research*, vol. 12, pp. 2825–2830, 2011.',
        'A. Radford et al., “Learning Transferable Visual Models From Natural Language Supervision,” in *Proc. International Conference on Machine Learning (ICML)*, 2021.',
        'E. Xie et al., “SegFormer: Simple and Efficient Design for Semantic Segmentation with Transformers,” in *Advances in Neural Information Processing Systems (NeurIPS)*, 2021.',
        'D. M’Raihi, S. Machani, M. Pei, and J. Rydell, “TOTP: Time-Based One-Time Password Algorithm,” IETF RFC 6238, 2011.',
        'OASIS, *Common Alerting Protocol Version 1.2*, OASIS Standard, 2010.',
        'OWASP Foundation, *Application Security Verification Standard (ASVS)*, version 4.0.3, 2021.',
        'R. W. Sinnott, “Virtues of the Haversine,” *Sky and Telescope*, vol. 68, no. 2, p. 159, 1984.',
        'FastAPI documentation, https://fastapi.tiangolo.com ; SQLAlchemy documentation, https://docs.sqlalchemy.org ; React documentation, https://react.dev ; Leaflet documentation, https://leafletjs.com.',
        'OpenStreetMap contributors, https://www.openstreetmap.org/copyright ; Natural Earth, https://www.naturalearthdata.com ; DataMeet Municipal Spatial Data (BBMP wards), https://github.com/datameet/Municipal_Spatial_Data.',
        'IndoFloods catchment shapefiles and gauge metadata, as supplied with the project (see the Data & Models view for the dataset registry).']

def build_refs(b):
    b.unnumbered('References')
    for i, r in enumerate(REFS, 1):
        para = b.d.add_paragraph(); pf = para.paragraph_format; pf.left_indent = Cm(1.0); pf.first_line_indent = Cm(-1.0); pf.space_after = Pt(5)
        b._runs(para, f'[{i}]  ' + r, 11.5)
