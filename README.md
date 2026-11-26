# Flood Digital Twin + RescueNet X 2.0

A flood-risk monitoring and emergency response platform that combines **flood prediction, geospatial mapping, citizen reports, AI-assisted image analysis, LoRa SOS simulation, incident management, rescue coordination, and emergency alerts**.

The system supports the workflow from **flood-risk assessment → incident verification → rescue triage → commander approval → dispatch → resolution**.

---

## 🚨 Key Features

- **Flood Risk Prediction**
  - Random Forest-based flood-risk classification.
  - Uses rainfall, humidity, and temperature.
  - Hold-out evaluation: **97.0%**
  - Cross-validation accuracy: **97.5%**
  - Water level is handled separately through gauge-based rules.

- **Flood Digital Twin**
  - Geospatial flood-risk visualization.
  - Catchment and flood-related spatial datasets.
  - Supports observed, predicted, historical, and simulated data.

- **AI Flood Photo Analysis**
  - Analyses submitted photographs for possible flooding.
  - Detection accuracy: **99.3%**
  - False-alarm rate: **7.3%**
  - Used as decision support during incident verification.

- **LoRa SOS Simulation**
  - Simulates emergency SOS packets.
  - Supports GPS-based locations and gateway trilateration.
  - Physical LoRa hardware is not required for the current setup.

- **Incident & Rescue Management**
  - Tracks incidents through a controlled lifecycle.
  - Supports verification, triage, approval, dispatch, tracking, and resolution.
  - Human approval is required for high-risk and larger incidents.

- **Emergency Alerts**
  - CAP 1.2-compatible alert generation.
  - Duplicate detection.
  - Severity-based escalation.
  - Commander/admin acknowledgement.

- **Local AI Supervisor**
  - Supports Ollama for local AI assistance.
  - Includes a rule-based fallback when Ollama is unavailable.

- **Role-Based Access**
  - Citizen
  - Volunteer
  - Operator
  - Commander
  - Rescue Officer
  - Admin

---

## 🔄 Incident Workflow

```text
REPORTED
   ↓
UNDER_VERIFICATION
   ↓
VERIFIED
   ↓
QUEUED
   ↓
TRIAGE_IN_PROGRESS
   ↓
PENDING_APPROVAL
   ↓
DISPATCHED
   ↓
IN_TRANSIT
   ↓
ON_SCENE
   ↓
RESOLVED
```

Additional outcomes:

```text
DUPLICATE
REJECTED
CANCELLED
```

Commander approval is required when:

- The incident involves **5 or more people**, or
- The severity is **HIGH** or **CRITICAL**.

Invalid incident state transitions are rejected by the API.

---

## 📊 Flood Prediction

The flood-risk model uses:

- Rainfall
- Humidity
- Temperature

Current evaluation:

| Metric | Result |
|---|---:|
| Hold-out evaluation | **97.0%** |
| Cross-validation | **97.5%** |

The model is intended for **risk classification**, not precise long-range flood forecasting.

Water level is handled separately through gauge-based warning and danger rules rather than being used as an ML input.

---

## 📷 AI Flood Photo Analysis

The image-analysis module provides an additional verification signal for citizen-submitted photographs.

Current evaluation:

| Metric | Result |
|---|---:|
| Flood detection | **99.3%** |
| False alarms | **7.3%** |

The system does **not** determine exact water depth from a photograph. Reported depth is provided separately by the incident reporter where required.

AI results are treated as decision support rather than automatic emergency decisions.

---

## 📡 LoRa SOS

The current LoRa functionality is a **simulation**.

Simulated SOS packets can include:

- SOS/device information
- GPS coordinates
- Gateway information
- Signal-related information
- Estimated position through trilateration

The current implementation does not require physical LoRa hardware.

---

## 📢 Emergency Alerts

The alert system supports **CAP 1.2-compatible XML**.

Features include:

- Severity classification
- Duplicate detection
- Escalation rules
- Commander/admin acknowledgement
- CAP XML generation

CAP endpoint:

```text
GET /api/alerts/{id}/cap
```

Current escalation timings:

| Severity | Escalation |
|---|---:|
| CRITICAL | 10 minutes |
| HIGH | 20 minutes |
| WARNING | 60 minutes |

---

## 🏷️ Data Labels

The platform distinguishes between different sources of information:

```text
OBSERVED
PREDICTED
HISTORICAL
SIMULATED
```

This helps distinguish real observations from model-generated and simulated data.

---

## 🛠️ Tech Stack

### Backend

- Python
- FastAPI
- SQLite
- SQLAlchemy
- Pydantic
- Scikit-learn
- PyTorch / computer-vision components
- Ollama

### Frontend

- React
- TypeScript
- Vite
- npm

### Data & Geospatial

- CSV datasets
- Shapefiles
- GeoJSON/geospatial data
- Catchment datasets
- Flood-risk datasets

### Emergency Communication

- LoRa SOS simulation
- CAP 1.2 alerts

---

## 📁 Project Structure

```text
rescuenet-x/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   ├── db/
│   │   ├── ml/
│   │   ├── services/
│   │   └── ...
│   │
│   ├── scripts/
│   ├── tests/
│   └── .env.example
│
├── rescuenet-x2/
│   └── frontend/
│
├── datasets/
│   └── ...
│
├── catchments_shapefiles_indofloods imag/
│   └── ...
│
├── docs/
│   └── ...
│
├── .gitignore
├── CONTRIBUTING.md
└── README.md
```

---

## ⚡ Quick Start

### Requirements

- Python **3.10+**
- Node.js **20.19+**
- npm
- Git

### 1. Clone the repository

```bash
git clone https://github.com/bhavaniv2750-dev/rescuenet-x.git
cd rescuenet-x
```

### 2. Backend

```powershell
cd backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Create the local environment file:

```powershell
Copy-Item .env.example .env
```

Start the backend:

```powershell
uvicorn app.main:app --reload
```

### 3. Frontend

Open another terminal:

```powershell
cd rescuenet-x2/frontend

npm ci
npm run dev
```

The frontend URL will be displayed by Vite in the terminal.

---

## ⚙️ Configuration

Local configuration is stored in:

```text
backend/.env
```

The repository provides:

```text
backend/.env.example
```

Use `.env.example` as the template for local configuration.

Typical configuration includes:

```text
DATABASE_URL
SECRET_KEY
RESCUENET_ADMIN_PASSWORD
SEED_DEMO_USERS
VITE_API_BASE_URL
```

**Never commit real passwords, API keys, tokens, or other secrets.**

The `.env` file is intentionally ignored by Git.

---

## 👤 Demo Accounts

Demo accounts can be enabled for local development/testing with:

```text
SEED_DEMO_USERS=true
```

Supported roles include:

```text
Citizen
Volunteer
Operator
Commander
Rescue Officer
Admin
```

Demo credentials should only be used for development/testing.

Before any real deployment:

- Disable demo-user seeding.
- Change default credentials.
- Configure secure secrets.
- Use appropriate production authentication and secret management.

---

## 🧪 Testing

The project includes automated backend and frontend tests.

Run backend tests:

```powershell
cd backend
pytest
```

Run the frontend test command configured in `package.json`.

Tests cover areas including:

- API behaviour
- Authentication
- Incident workflows
- Alert handling
- ML-related functionality
- Frontend behaviour

---

## 🗺️ Geospatial Data

The project contains flood and catchment-related geospatial datasets.

Shapefiles normally consist of multiple companion files, for example:

```text
.shp
.shx
.dbf
.prj
```

Keep shapefile companion files together.

**Do not rename, move, or partially delete tracked shapefile data without checking the application's dataset references.**

---

## ⚠️ Known Limitations

This project is a development and decision-support platform and is **not a replacement for official emergency-management infrastructure**.

Current limitations include:

- Flood projections are heuristic and should not be treated as authoritative forecasts.
- The current flood model does not provide reliable long-range forecasting.
- Water-level warnings depend on available gauge information.
- LoRa communication is currently simulated.
- Photo analysis can produce false positives and false negatives.
- Difficult visual conditions may reduce image-analysis performance.
- Exact water depth cannot be determined directly from photographs.
- The local AI supervisor depends on Ollama when available and uses deterministic rules as fallback.
- SQLite is suitable for development and smaller deployments but may need replacement for large-scale production.
- Development configurations may use localhost services and development CORS settings.

---

## 🤝 Contributing

Contributions are welcome.

Recommended workflow:

```text
Create branch
     ↓
Make changes
     ↓
Run tests
     ↓
Review changes
     ↓
Commit
     ↓
Open Pull Request
```

Before submitting a pull request:

- Keep changes focused.
- Run relevant tests.
- Do not commit `.env` or other secrets.
- Do not unnecessarily modify datasets.
- Keep shapefile companion files together.
- Update documentation when changing ML behaviour or evaluation.
- Do not tune models using the test set.
- Review security-sensitive changes carefully.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution guidelines.

---

## 🔒 Security

Never commit:

```text
.env
API keys
Passwords
Tokens
Private credentials
Production secrets
```

If a secret is accidentally committed, revoke or rotate it immediately and remove the exposed secret from the repository history as appropriate.

---

## 📄 License

No open-source license has been selected for this repository yet.

Until a license is added, the source code should not be assumed to be freely reusable, modified, or redistributed.

---

## 🚧 Project Status

**Active development**

Flood Digital Twin + RescueNet X 2.0 currently integrates flood-risk analysis, geospatial visualization, citizen reporting, AI-assisted photo verification, SOS simulation, emergency alerts, incident management, and rescue coordination into a single platform.
