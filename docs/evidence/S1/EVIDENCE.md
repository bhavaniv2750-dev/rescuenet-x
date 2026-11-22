# S1 evidence

## Tests (isolated throw-away databases)
| Suite | Result |
|---|---|
| Full backend suite | 324 passed, 1 skipped (live Ollama) |
| P0 dispatch-safety (`test_p0_safety.py`, `test_team_selection.py`, files unchanged) | 66 passed |
| S0 security (`test_public_media.py`, `test_public_refs.py`) | 53 passed |
| New: policy invariants (`test_permission_policy.py`) | 36 |
| New: endpoint × principal matrix (`test_endpoint_authorization.py`): all 71 endpoints as guest and 7 roles, hand-written expectations + golden | 5 |
| New: resource scoping (`test_resource_scoping.py`) | 37 |
| New: stale access (`test_stale_access.py`) | 10 |
| New: service-level authorization (`test_service_authorization.py`) | 23 |
| New: production environment guard (`test_environment_guard.py`, fresh interpreter per case) | 7 |
| Frontend `npm run build` | passes |
| Browser: admin, developer, commander, officer sessions | no refused API calls; navigation matches the matrix |

## Screenshots
`01_admin_console_1366.png` (administrator: accounts/audit/diagnostics, no operations pages),
`02_developer_diagnostics_1366.png` (developer: diagnostics and data & models only),
`03_commander_overview_1366.png`, `04_officer_missions_1366.png`.

## Notes
- The expectation table in `test_endpoint_authorization.py` was written independently of the observed behaviour; it matched on
  the first run for every endpoint, and a new endpoint without a decision fails the suite.
- Matrix: `docs/security/PERMISSION_MATRIX.md`. Rules, limitations, migration: `docs/security/S1_AUTHORIZATION.md`.
