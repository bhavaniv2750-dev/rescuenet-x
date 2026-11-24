# Running RescueNet X 2.0 on Windows (PowerShell)

**Status of this guide:** written and checked against the repository's own scripts. It has **not** been executed on a Windows laptop by the author of this
document (the development environment is Linux). If a step differs on your machine, treat the script's own `--help` as the source of truth.
No secret value appears in this guide: you generate your own.

Requirements: Git, Python 3.12 or newer, Node.js 20 or newer, PowerShell. Open **two** PowerShell windows (one for the API, one for the web app).

## 1. Get the code
```powershell
cd C:\path\to\rescuenet-x
git fetch origin
git checkout extra-features
git pull origin extra-features
```

## 2. Backend dependencies
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if scripts are blocked: Set-ExecutionPolicy -Scope Process RemoteSigned
pip install -r requirements.txt
```

## 3. Frontend dependencies
```powershell
cd ..\rescuenet-x2\frontend
npm ci
```

## 4. Local security keys and settings
Create `backend\.env` (it is git-ignored; never commit it). Use `.env.example` in the repository root as the list of options. For local development:
```powershell
cd ..\..\backend
python scripts\mfa_keys.py generate          # prints a NEW key: copy it into MFA_ENCRYPTION_KEYS below, nowhere else
python -c "import secrets; print(secrets.token_urlsafe(48))"      # a long random value for JWT_SECRET
```
Minimum `backend\.env` for development (replace the placeholders with the values you just generated):
```
RESCUENET_ENV=development
JWT_SECRET=<your generated value>
MFA_ENCRYPTION_KEYS=dev:<your generated key>
SEED_DEMO_USERS=false
```
`RESCUENET_ENV=production` additionally needs `PUBLIC_APP_URL`, `CORS_ORIGINS_PRODUCTION` and a real email provider; check any configuration with
`python scripts\check_config.py` (it prints no secrets).

## 5. Back up and migrate an existing database
If you already have `backend\rescuenet.db` from an earlier version, **back it up first**; migration also takes an automatic verified backup before changing anything.
```powershell
python scripts\backup_db.py --label before-f-series
python scripts\backup_db.py --verify <path printed above>
```
The server upgrades the schema (Alembic, revision `0006`) when it starts. To restore, use `python scripts\restore_db.py --help`.
Older databases may contain **demo accounts whose password was published in earlier releases**. Find and disable them (dry run first, nothing is deleted):
```powershell
python scripts\disable_demo_accounts.py
python scripts\disable_demo_accounts.py --apply --confirm "DISABLE DEMO ACCOUNTS" --reason "local cleanup" --i-am-authorized
```
If that leaves no administrator, create one: `python scripts\bootstrap_admin.py --help`.

## 6. Isolated development accounts (optional, simulated)
For a **fresh, empty** development database only, simulated demo accounts can be created. Use a separate database file so your real data is never touched:
```powershell
$env:DATABASE_URL = "sqlite:///./demo-dev.db"
$env:SEED_DEMO_USERS = "true"
$env:DEMO_USER_PASSWORD = "<choose a password for this throw-away database>"
```
Privileged demo accounts (admin, developer, commander, operator, officer) still must set up an authenticator app at first sign-in. Delete `demo-dev.db` when done.
Real staff are created with `python scripts\account_admin.py invite --help` (one-time link) and the first administrator with `scripts\bootstrap_admin.py`.

## 7. Start the API (window 1)
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Check http://127.0.0.1:8000/api/health and http://127.0.0.1:8000/docs.

## 8. Start the web app (window 2)
```powershell
cd rescuenet-x2\frontend
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000/api"
npm run dev
```
Open the address Vite prints (normally http://localhost:5173). Both experiences use the same app:
* Public portal: `http://localhost:5173/` and `/public/...` (no account needed to read warnings or report an emergency)
* Operations console: sign in with a staff account; the server then sends you to `/console/...`

The browser needs internet access for the OpenStreetMap background tiles. Offline it shows the overlays plus a notice; offline maps are not implemented.

## 9. Check that Ollama is available (optional)
The AI supervisor works without Ollama (rule-based fallback, always requiring commander approval). To use a local model you must run Ollama yourself:
```powershell
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```
The console's AI Supervisor page shows "Language model reachable" only when the server can really connect. This project has **not** verified a live Ollama integration.

## 10. Tests
```powershell
cd backend
python -m pytest -q                                 # full suite (uses a throw-away database)
python -m pytest backend\tests\test_ollama_supervisor.py -k real_local_ollama -rs   # the live-Ollama test: skipped unless Ollama is reachable
cd ..\rescuenet-x2\frontend
npm test; npm run build
```
The live-Ollama test skips itself with the reason if the daemon is unreachable. Whether it passes against your model has not been tested by the author.
