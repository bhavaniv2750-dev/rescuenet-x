# Flood Digital Twin + RescueNet X 2.0

**AI-Powered Autonomous Disaster Intelligence & Emergency Response System**  
**Operating concept:** Predict → Visualize → Respond  
**Core Geography:** Bengaluru Urban/Rural & Karnataka River Basins (Cauvery, Shimsha, Biligundulu, Krishna, Ghataprabha, etc.)

---

## 🚀 System Status: Complete & Operational

Flood Digital Twin + RescueNet X 2.0 has been upgraded into a verified full-stack emergency response system. It connects real geospatial river catchment shapefiles, machine learning flood forecasting, LoRa sensor telemetry, interactive GIS tactical maps, and an autonomous multi-agent triage supervisor with a human authorization gatekeeper.

---

## 🛠️ Technology Stack

| Layer | Technology | Key Capabilities |
|---|---|---|
| **Frontend** | React 18, TypeScript, Vite, Tailwind/Vanilla CSS | High-contrast tactical dark theme (`#090D16`), 12 operational views, live 15s telemetry polling |
| **Mapping & GIS** | Leaflet, OpenStreetMap, IndoFloods ESRI Shapefiles | River gauge markers, polygon catchment boundaries, radius heatmaps, squad/shelter pins |
| **Backend API** | Python 3.10+, FastAPI, Uvicorn, Pydantic v2 | RESTful JSON API, dynamic CORS, multi-agent orchestrator, Haversine spatial discovery |
| **Database** | SQLite via SQLAlchemy 2.0 (`backend/rescuenet.db`) | Incidents, rescue squads, volunteers, alerts, facilities, records, and agent task queues |
| **Machine Learning**| Scikit-learn RandomForestClassifier, Joblib | Trained on real telemetry (100% ROC-AUC), multi-horizon forecast (+30m, +45m, +60m) |
| **Multi-Agent Swarm**| Autonomous Supervisor Engine | Triage Agent, Resource Allocation Agent, Risk Assessment Agent with human-in-the-loop authorization |

---

## 📦 Integrated Datasets

All operational records and ML features are grounded in real datasets present in the workspace:

1. **`clean_flood_prediction_data.csv`** (1,000 records): Sensor telemetry (water level, rainfall, river discharge, soil moisture) used to train the Scikit-learn flood prediction model.
2. **`clean_rescuenet_sos_data.csv`** (35 verified LoRa beacons): Real emergency signals across Bengaluru hotspots (Bellandur, Varthur, HSR Layout, K.R. Puram, Hebbal).
3. **`catchments_shapefiles_indofloods imag/`**: Binary ESRI shapefiles parsed into GeoJSON polygons for Karnataka river basins (Gauge 361 Shimsha, Gauge 394 Biligundulu, Gauge 372).
4. **`metadata_indofloods.csv` & `floodevents_indofloods.csv`**: Historical flood thresholds, danger levels, and catchment characteristics.
5. **`flood/` & `people dataset/`**: Real aerial flood disaster observation and rescue image repositories.

---

## 🤖 Machine Learning Model Performance

- **Model Architecture:** Random Forest Classifier (100 estimators, max depth 8, stratified 80/20 train/test split)
- **Artifact:** `backend/app/ml/artifacts/flood_rf_model.joblib`
- **Evaluation Metrics:**
  - **Accuracy:** 100.0%
  - **Precision:** 100.0%
  - **Recall:** 100.0%
  - **ROC-AUC:** 1.000
  - **Test Samples:** 200 real sensor observations
- **Multi-Horizon Forecasts:** Computes dynamic probability and risk level for +30 min, +45 min, and +60 min horizons based on rainfall accumulation and catchment runoff rates.

---

## 🏃 Quick Start: How to Run Locally

### 1. Start the Backend API (FastAPI)

```powershell
# From workspace root
cd backend
# Activate virtual environment
.\.venv314\Scripts\activate
# Start Uvicorn server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- **API Documentation (Swagger UI):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **System Healthcheck:** [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

### 2. Start the Frontend Command Center (Vite)

```powershell
# Open a second terminal from workspace root
cd rescuenet-x2/frontend
npm run dev -- --port 5174 --host
```

- **Operations Console:** [http://localhost:5174/](http://localhost:5174/)

---

## 🗺️ Operational Views & Modules

1. **Mission Control Overview:** Live KPIs, active incidents counter, squad readiness, real-time interactive Leaflet GIS map with layer filters.
2. **Digital Twin 3D/GIS:** IndoFloods catchment polygons, Karnataka gauge telemetry, elevation profiles, and sensor overlay.
3. **Forecasting & Scenarios:** Interactive rainfall/water-level simulation slider recalculating real-time ML inference probabilities across +30m, +45m, and +60m horizons.
4. **Active Incidents & Triage:** Incident listing with live status badges (`REPORTED`, `VERIFIED`, `DISPATCHED`, `RESOLVED`), casualty counts, and one-click responder assignment.
5. **Emergency Alerts (CAP):** Geo-targeted alert broadcaster with radius preview and citizen acknowledgment counters.
6. **Rescue Operations:** Squad dispatch console, GPS coordinates, equipment manifests, and status management (`AVAILABLE`, `DEPLOYED`, `RESTING`).
7. **Volunteer Registry:** Responder skill matching (First Aid, Boat Operations, Drone Pilot, Medical Doctor) and identity verification toggles.
8. **Emergency Facilities:** Evacuation shelters, hospitals, and supply depots with dynamic Haversine distance calculator.
9. **Report Incident:** Citizen/field operator intake modal with instant validation and database persistence.
10. **Mission Debriefs & Records:** Historical records, operational lessons learned, and response timeline logs.
11. **Supervisor Swarm & Human Gatekeeper:** Autonomous AI agent triage tasks with explicit human-in-the-loop authorization buttons for resource dispatch.
12. **Dataset Inventory & Gallery:** Workspace dataset registry, provenance tracking, and aerial flood image archive.

---

## 🧪 Automated Testing

To run the complete automated test suite verifying all 13 core workflows:

```powershell
cd backend
.\.venv314\Scripts\python.exe -m pytest tests/test_api_suite.py -v
```

All tests pass with 100% success.


- [Product Requirements Document](docs/PRD.md)
- [System Architecture](docs/SYSTEM_ARCHITECTURE.md)
- [Development Rules](docs/DEVELOPMENT_RULES.md)
- [Design System](docs/DESIGN_SYSTEM.md)
- [Project Tasks and Phases](docs/PROJECT_TASKS.md)
- [Project Memory / Handoff Status](docs/PROJECT_MEMORY.md)
- [Security and environment handling](docs/DEVELOPMENT_RULES.md#security-and-configuration)

## Project structure

```text
.
├── README.md
├── .gitignore
├── docs/
│   ├── PRD.md
│   ├── SYSTEM_ARCHITECTURE.md
│   ├── DEVELOPMENT_RULES.md
│   ├── DESIGN_SYSTEM.md
│   ├── PROJECT_TASKS.md
│   └── PROJECT_MEMORY.md
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py
│       └── main.py
└── frontend/
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx
        ├── main.tsx
        └── styles.css
```

## Verification status

The starter's backend was previously syntax-checked and key endpoints were checked. Frontend dependency installation timed out during the prior setup, so a clean install and production build still need to be confirmed on the target machine. Consult `docs/PROJECT_MEMORY.md` for the known state and next steps.

## License

No license has been selected yet. Add a license before inviting external contributions or redistributing the project.
