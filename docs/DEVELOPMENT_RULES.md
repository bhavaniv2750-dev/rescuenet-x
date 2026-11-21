# Development Rules

## 1. General principles

1. **Safety first:** the software supports emergency decision-making; it must not imply authority or certainty it does not have.
2. **Simulation is explicit:** label simulated, synthetic, derived, stale, and real data distinctly in API payloads and UI.
3. **Human accountability:** consequential actions (dispatch, alert escalation, volunteer assignment, incident closure) require an authorized human decision.
4. **Small, testable changes:** make focused changes, explain why, and verify affected flows before marking work complete.
5. **Traceability:** record source, timestamp, actor, state transition, and reason for operationally significant changes.
6. **Accessibility:** use keyboard-accessible controls, clear focus states, readable contrast, and text labels in addition to color.
7. **No invented capability:** documentation, UI, and demos must accurately describe what is implemented versus planned.

## 2. Technology and coding standards

### Frontend
- Use TypeScript; avoid `any` unless justified and isolated.
- Use functional React components and hooks; keep components focused.
- Keep API calls out of presentation components where practical; use a typed service layer as it grows.
- Represent loading, empty, stale, error, and success states explicitly.
- Validate forms on both client and server; client validation is not a security boundary.
- Avoid hardcoded secrets and environment-specific URLs in source.
- Keep responsive behavior and keyboard navigation in scope for each feature.

### Backend
- Use Python type hints and Pydantic request/response schemas.
- Separate validation, business rules, persistence, and external integrations as the codebase grows.
- Use parameterized queries/ORM facilities; never build SQL from raw user input.
- Return appropriate HTTP status codes and sanitized error messages.
- Add tests for normal, invalid, missing-data, stale-data, and permission-denied cases.
- Use timezone-aware timestamps (UTC for storage where feasible) and document units for water level/rainfall.
- Add request size/time limits for file uploads and validate MIME type plus actual file content.

### Naming and formatting
- Python: `snake_case` functions/variables/modules, `PascalCase` classes.
- TypeScript/React: `PascalCase` components/types, `camelCase` variables/functions.
- Use descriptive names; avoid unexplained abbreviations and giant functions.
- Keep user-facing copy direct, actionable, and consistent with the design system.
- Prefer formatting/linting tools once configured; do not claim a tool is active until it exists in project config.

## 3. Project structure rules

- Keep frontend and backend dependencies separate.
- Place product and implementation decisions in `docs/` and update them when behavior changes.
- Avoid putting all future business logic in `main.py`; split into routers/services/repositories when the module becomes difficult to test.
- Keep model files, datasets, uploaded evidence, and generated artifacts out of Git unless explicitly reviewed and intended for version control.
- Store tests alongside the relevant layer or in clearly named `tests/` directories.
- Every feature should define API contract, UI states, validation, failure handling, and tests.

## 4. Security and configuration

- `.env`, `.env.*`, credentials, private keys, local databases, uploads, and runtime directories are ignored by `.gitignore`.
- A safe `.env.example` may be committed only if it contains variable names and dummy/blank values—never real credentials.
- Do not put secrets in frontend `VITE_*` variables; they are exposed to browser clients.
- Keep secret-bearing provider integrations on the backend and use least-privilege credentials.
- If a secret is committed accidentally, revoke/rotate it immediately and review repository history.
- Add authentication and role-based authorization before any real multi-user or sensitive operational deployment.
- Minimize collection of personal data; protect survivor and volunteer location/contact details and define retention rules.
- Log security-relevant events without logging passwords, tokens, or unnecessary sensitive content.

## 5. Data and model standards

- Every dataset/model must document source, license, coverage, time range, units, preprocessing, limitations, and owner.
- Keep training, validation, and test splits time-aware where temporal leakage is possible.
- Report baselines and relevant metrics on held-out data; do not fabricate results or display aspirational metrics as measured performance.
- Show forecast horizon, model/version, input freshness, uncertainty, and known coverage limitations.
- Monitor missing values, sensor drift, geographic mismatch, and failed ingestion.
- CV output must include a reviewable status and must not be treated as confirmed damage without verification.

## 6. Git workflow

- Use feature branches for substantial changes and descriptive commits (for example `feat: add incident filters`).
- Review `git status` and `git diff` before committing.
- Never force-add `.env`, local databases, credentials, uploads, or large unreviewed datasets.
- Keep commits focused; update README/docs for behavior, setup, or API changes.
- Before release, run backend tests, frontend build, secret scan, and dependency review.

## 7. Definition of done

A task is complete only when implementation, validation, failure states, tests (where applicable), documentation, and demo-vs-real labeling are addressed. Record known gaps instead of hiding them.
