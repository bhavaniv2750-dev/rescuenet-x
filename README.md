# Flood Digital Twin + RescueNet X 2.0

Flood risk mapping and rescue coordination for Bengaluru and Karnataka.
Dr. ACS College of Engineering, Dept. of CSE (Data Science), VTU.

The system helps a rescue control room go from **warning** to **dispatch**: it shows flood risk on a map,
takes reports from citizens and from LoRa SOS beacons, checks photos with AI, suggests which team to send,
and makes a human commander approve the dispatch.

## What it is, and what it is not

| It does | It does not |
|---|---|
| Predicts flood risk from rainfall, humidity and temperature (97.5% cross-validated accuracy, see [model evaluation](docs/model_evaluation.md)) | Read live river gauges or weather stations. There is no live sensor feed; data is refreshed from the database every 15 seconds |
| Locates LoRa SOS packets, from GPS or by trilateration from 3 or more gateways | Talk to real LoRa hardware. Beacons and packets in the sample data are simulated |
| Detects floods in photos (99.3% of the 809 project photos; 7.3% false alarms on 300 non-flood scenes, see [vision evaluation](docs/vision_evaluation.md)) | Measure water depth from a photo. The reporter chooses the depth |
| Shows warnings in the app and exports each one as CAP 1.2 XML | Send SMS, e-mail or push messages |
| Suggests a team with a local LLM (Ollama) and falls back to rules when it is offline | Dispatch anything without a commander's approval when 5 or more people are affected, or severity is HIGH or CRITICAL |

Every record carries a data label: **OBSERVED** (entered by a person or device), **PREDICTED** (model output) or
**SIMULATED** (sample data shipped with the project). Sample incidents, beacons, alerts and some facilities are SIMULATED.

## Quick start

You need Python 3.10 or newer (tested on 3.13) and Node.js 20.19 or newer (tested on 22).

**1. Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The first start creates `backend/rescuenet.db`, loads the sample data and the demo accounts.
API documentation: <http://127.0.0.1:8000/docs>. Health check: <http://127.0.0.1:8000/api/health>.

**2. Frontend** (second terminal)

```bash
cd rescuenet-x2/frontend
npm ci
npm run dev
```

Open <http://localhost:5173>.

**3. Optional extras**

```bash
# flood photo models (about 105 MB). They also download on first use.
python scripts/download_vision_model.py       # run from backend/

# local AI supervisor. Without it, triage uses the rule-based fallback.
ollama pull qwen3:4b-instruct
```

Copy `.env.example` to `backend/.env` to change settings.

## Sign-in portals and roles

The sign-in page has three portals. An account can only sign in through its own portal.

| Portal | Role | Can do |
|---|---|---|
| **Citizens & Volunteers** (self sign-up) | Citizen | See warnings, shelters, forecasts; report an emergency; follow their own reports |
| | Volunteer | Same as citizen. Must be **verified** by staff before being assigned to a rescue |
| **Rescue Department** (created by an admin) | Operator | Run the control room: verify and dispatch incidents, run AI triage, issue alerts, manage volunteers and facilities |
| | Commander | Everything an operator does, plus **approve or decline dispatches**, acknowledge alerts, read the audit log |
| | Rescue officer | See their team's missions and report progress (en route, on scene, resolved) |
| **Admin & Developers** | Admin | Everything above, plus accounts, system diagnostics, settings, deleting incidents |

Visitors can also continue **without signing in** to read warnings and shelters or report an emergency.

**Accounts and onboarding (S5).** There are no built-in accounts and no default passwords.
- Citizens and volunteers register themselves.
- The first administrator is created once, on the server, by a person with shell access: `python scripts/bootstrap_admin.py --help`.
- Every other staff, administrator or developer account is created by **invitation**: a server operator runs
  `python scripts/account_admin.py invite ...` and hands over a one-time link; the owner chooses their own password, verifies their
  email address and sets up two-step sign-in before the account can do anything (see `docs/security/S5_ACCOUNTS_AGENCIES.md`).
- Development only: `SEED_DEMO_USERS=true` with `RESCUENET_ENV=development` creates **simulated** demo accounts on an empty
  database, with the password you set in `DEMO_USER_PASSWORD` or a random one printed once to the console. Production refuses to
  start with it on. Databases created by older versions contain demo accounts whose password was published in earlier releases:
  disable them with `python scripts/disable_demo_accounts.py` (a dry run by default).

Passwords are hashed with PBKDF2-SHA256, sessions use signed tokens, and an account locks for 5 minutes after 5 wrong passwords.

## How an incident moves

```
REPORTED -> UNDER_VERIFICATION -> VERIFIED -> QUEUED -> TRIAGE_IN_PROGRESS
         -> PENDING_APPROVAL -> DISPATCHED -> IN_TRANSIT -> ON_SCENE -> RESOLVED
```

Side exits: `DUPLICATE`, `REJECTED` (can be re-queued), `CANCELLED`. Invalid jumps are refused.
Incidents that need approval (5 or more people, or HIGH or CRITICAL) reach `DISPATCHED` only through a commander's approval of the
supervisor task. The LLM can suggest, but a fixed rule decides whether approval is needed. Every state change,
approval, alert and account action is recorded in the audit log.

## Alerts

Alerts are shown in the app and exported as CAP 1.2 XML (`GET /api/alerts/{id}/cap`). A new alert that duplicates one already in force
(same title, or same severity within 1 km in the last 30 minutes) is refused. An unacknowledged CRITICAL, HIGH or WARNING alert is
flagged for escalation after 10, 20 or 60 minutes. Only a commander's or administrator's acknowledgement changes an alert's status; other people
add to a "seen by" count.

## Tests

```bash
cd backend
python -m pytest -q
```

68 tests pass; 1 more is skipped unless Ollama is running, and 3 more are skipped until the photo models are downloaded.
Measure the models yourself with `scripts/evaluate_vision.py` and by retraining (`FloodModelService.train_model`).

## Project layout

```
backend/
  app/api/routes/     FastAPI routes (auth, incidents, agents, teams, volunteers, alerts, facilities, vision, ...)
  app/services/       lifecycle, audit, alerting (CAP), trilateration, vision, Ollama supervisor
  app/ml/             flood model and its saved evaluation
  app/db/             tables, migration, sample data, beacon registry
  scripts/            model download, evaluation, prompt encoding
  tests/
rescuenet-x2/frontend/ React 19 + TypeScript + Vite, Leaflet maps
docs/                 model_evaluation.md, vision_evaluation.md and earlier design notes
flood/, "Flood Prediction Dataset"/, "flood pred detc rescue net clean dataset"/, ...  datasets
```

The other files in `docs/` (PRD, architecture, tasks) are earlier design notes and may be out of date. This README and the two
evaluation files describe the current system.

## Known limitations

- The flood model cannot forecast ahead on this dataset (next-hour accuracy is close to chance because the rows are nearly independent hours), so the +30, +45 and +60 minute values are a runoff formula, not machine learning. It was trained on data from one station.
- River gauge stations carry warning and danger levels only, not current readings.
- `clean_rescuenet_sos_data.csv` has Mumbai coordinates, so it is kept for reference only; the Bengaluru beacons are simulated.
- Photo analysis uses pretrained models that were not fine-tuned on flood photos. Muddy water can be under-counted and some street and canal scenes cause false alarms.
- SQLite is meant for one server. Use a client-server database for anything larger.
- `DEBUG=True` and open CORS for localhost are development settings.

## License

No license has been selected yet. Add one before redistributing the project.
