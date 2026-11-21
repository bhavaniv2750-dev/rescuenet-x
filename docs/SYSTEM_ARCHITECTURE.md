# System Architecture

## 1. High-level architecture

```text
Public data feeds / approved field reports / demo generators
                         |
                         v
              Data adapters + validation
                         |
                         v
 React + TypeScript UI <-> FastAPI REST API
          |                    |
          |                    +--> Forecast service (prototype; model interface later)
          |                    +--> Incident / alert / mission services
          |                    +--> Supervisor task service
          |                    +--> Facility search service
          |                    +--> Image intake / CV adapter (placeholder currently)
          |                    +--> Persistence layer
          |                               |
          v                               v
 OpenStreetMap map tiles             SQLite (local prototype)
                                          |
                                          +--> PostgreSQL + PostGIS (scale path)
```

The current repository is a compact prototype. The service names above describe logical boundaries to preserve as the application grows; they do not imply that every service is already split into a separate module or that external data feeds are connected.

## 2. Main components

- **Frontend (`frontend/`)**: React + TypeScript single-page operations console; Vite development server/build; map rendering and operational panels.
- **API (`backend/app/main.py`)**: FastAPI routes, request validation, prototype business logic, and persistence currently concentrated in a small entry module.
- **Persistence**: SQLite for local prototype records. Keep database access behind a repository/data-access boundary as the project expands.
- **Forecast adapter**: exposes short-horizon estimates with metadata and uncertainty; replace demo logic with a separately evaluated model pipeline.
- **Image analysis adapter**: accepts image metadata; placeholder analysis only until a trained model is integrated.
- **Data adapters**: future connectors for approved weather/rainfall/water-level/terrain feeds. Each connector should normalize timestamps, units, coordinates, provenance, and freshness.
- **Map layer**: OpenStreetMap tiles; tile access requires internet. Verify applicable attribution and usage policies.

## 3. Technology stack

| Concern | Current / planned technology | Notes |
|---|---|---|
| UI | React, TypeScript, Vite | Current starter |
| Styling | CSS | Current stylesheet is `frontend/src/styles.css` |
| Geographic base map | OpenStreetMap tiles | No claim of offline tile availability |
| Backend | Python, FastAPI, Uvicorn | Current starter |
| Validation | Pydantic via FastAPI models | Use explicit schemas for API contracts |
| Local database | SQLite | Prototype only; consider migrations as schema grows |
| Spatial database | PostgreSQL + PostGIS | Future production-oriented path |
| Forecast/CV | Python model adapters; library choice based on evaluation | Do not hardwire unvalidated model claims into UI |
| Testing | pytest + API client; frontend test tooling to be selected | Add as part of implementation phases |
| Packaging/deployment | Docker/CI may be added later | Not currently assumed present |

## 4. Proposed project structure

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
│       └── main.py                 # current compact API entry point
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── App.tsx
        ├── main.tsx
        └── styles.css
```

As complexity increases, refactor toward:

```text
backend/app/
├── main.py
├── api/routes/          # versioned routers by domain
├── core/                # configuration, logging, security
├── schemas/             # request/response DTOs
├── models/              # persistence models
├── repositories/        # database queries
├── services/            # business rules
├── integrations/        # external feeds, notification providers
├── ml/                  # forecast/CV interfaces and evaluation metadata
└── tests/
frontend/src/
├── app/                 # routing and app shell
├── components/          # shared UI components
├── features/            # map, incidents, alerts, missions, facilities
├── services/            # typed API client
├── hooks/
├── types/
└── styles/
```

Do not create empty abstraction layers solely for appearance; introduce modules when they improve testability or maintainability.

## 5. Data flow

1. A data adapter or user report submits source data with timestamp, coordinates, provenance, and validation state.
2. The API validates schema, permissions, bounds, and freshness.
3. Domain services create/update incidents, alerts, missions, tasks, or forecast records.
4. The repository persists state and audit events.
5. The API returns typed responses with status and provenance metadata.
6. The UI renders records with labels for real/simulated/derived data, freshness, uncertainty, and verification status.

## 6. API design expectations

- Keep routes resource-oriented and return consistent HTTP status codes.
- Version public API routes before breaking changes (for example `/api/v1/...`).
- Use typed request/response schemas and stable identifiers.
- Validate coordinates, time ranges, upload size/type, and user-supplied text.
- Return explicit source/freshness/uncertainty fields for risk estimates.
- Add pagination/filtering for growing incident and audit datasets.
- Do not expose stack traces, internal file paths, secrets, or sensitive personal details.

## 7. Deployment and scale path

Local development: Vite frontend + Uvicorn API + SQLite. Before multi-user deployment, add configuration management, authentication/authorization, migrations, structured logging, backups, monitoring, rate limits, CORS restrictions, HTTPS, and a managed database. Use PostGIS when geospatial query complexity or concurrent use exceeds the SQLite prototype's needs.
