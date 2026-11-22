# S1: permission model and role separation

Single source of truth: `backend/app/core/permissions.py`. The full role × permission and endpoint × role tables are in
[PERMISSION_MATRIX.md](PERMISSION_MATRIX.md) (generated; regenerate with `python backend/scripts/generate_permission_matrix.py`).

## How authorization works
1. **Routes** declare `require_permission(P.…)` (`app/api/deps.py`). The guard reads the user's role **from the database on
   every request**, never from the token, so role changes, team reassignment and deactivation apply on the next request.
2. **Resource scope** is checked in the handler: officers reach only incidents/evidence/records of their own team, citizens
   and volunteers only their own reports and photos, others get 404 (not 403) so existence is not revealed.
3. **Services re-check** (`services/dispatch.py`, `services/incident_lifecycle.py`): dispatching needs `dispatch.assign`,
   claiming commander approval needs `dispatch.approve`; the AI supervisor (`AGENT`) and `SYSTEM` hold neither. This holds
   even if a future route forgets its dependency.
4. **Frontend navigation** is a convenience only. The API refuses everything the role may not do.

## Separation of duties (enforced by `tests/test_permission_policy.py`)
| Rule | Result |
|---|---|
| Administrator: identity and system management only | no dispatch, triage, approval, alert publish/resolve, incident or evidence view, volunteer/record data |
| Developer: diagnostics only | `system.diagnostics`, `data.view`, `supervisor.view` (health); no incident, citizen, volunteer, account or dashboard data, no rescue controls |
| Commander approval | `dispatch.approve` held by COMMANDER only |
| Rescue officer | assigned missions, their evidence, own-team records; field progress states only |
| Citizen / volunteer | own reports and photos plus public resources |
| Guests | report, track (with code), read public information |

## Changes in behaviour (intentional)
- ADMIN lost: incidents, evidence, dispatch, triage, approval, alerts, volunteers, facilities, records, supervisor.
  ADMIN keeps: user management, audit log, diagnostics, dashboard summary, data & models, incident deletion (see limitations).
- RESCUE_OFFICER lost: listing/reading incidents of other teams, history of other incidents, beacons, volunteers,
  datasets, supervisor roster. Records list/summary/create are limited to their own team and assigned missions.
- Commander-only: records CSV export, alert control-room acknowledgement, risk reduction of approval-gated incidents.
- New role `DEVELOPER` (admin/developer portal). `/auth/me` and sign-in now include `permissions`.
- New `GET /auth/team-options` (admin): squad id and name only, so officer accounts can be created without squad visibility.
- `/auth/portals` shows demo credentials only when `RESCUENET_ENV=development`.

## Production safeguards added in S1 (`tests/test_environment_guard.py`)
- `RESCUENET_ENV` must be exactly `development` or `production`; unset means production.
- In production demo accounts are never created (even with `SEED_DEMO_USERS=true`) and no demo credentials are advertised.
- In production `/api/incidents/lora` returns 503 until `LORA_GATEWAY_KEY` is set; the key is compared in constant time.

## Role changes and deactivation
Enforced and tested now: demotion/promotion/deactivation/reactivation/team reassignment take effect on the next request with
the old token; a token whose role claim differs from the database role gains nothing; admins cannot disable or demote
themselves; role changes and admin password resets are audited.
**Limitation until S2:** there is no token revocation. A token already issued to a still-active account stays valid until it
expires (480 minutes), also after a password change (pinned by `test_KNOWN_LIMITATION_*`). S2 introduces sessions and token
versioning and changes this on purpose (no grace period, immediate invalidation with clear re-login messaging).

## Remaining limitations (honest list)
1. **Admin credential control:** an administrator can create staff accounts and reset their passwords. That is a path to
   operational power (provision a commander, then sign in as them). Audited, but not prevented. Closed by S3 (self-service
   recovery, no admin-set passwords for staff), S4 (mandatory MFA for commander/admin/developer) and S5 (invitations).
2. **MFA and verified-contact requirements** for privileged roles are not enforced yet (S3/S4); the plan requires them.
3. **Demo accounts that already exist** in a database are not disabled by S1 (S5 does this with a sanitized summary). The
   demo password is still the default in `config.py` and in git history; never use it for real.
4. **Operators and commanders publish alerts directly** (existing behaviour). The draft → review → approve workflow and
   targeting are Phase E; unapproved mass publication by other roles is impossible, but a single operator can still publish.
5. **Incident deletion** remains an admin permission (`incident.delete`), audited. Consider removing it when retention rules exist.
6. **Volunteer personal data** is visible to operators and commanders (need-to-know masking is Phase E).
7. **Rate limits** are per process (S0). **Per-user permission grants** are not implemented (S5); roles are fixed bundles.
8. `/api/incidents/lora` is open when no gateway key is set in development.

## Migration impact
No database schema change and no data migration. `role` is a plain string, so `DEVELOPER` needs no migration. Existing
ADMIN accounts keep working but lose operational endpoints (listed above); staff who relied on an admin account for
dispatch must use a COMMANDER or OPERATOR account. Existing databases have no demo developer account (demo seeding only
runs on an empty database); create one with the admin console. Rollback: revert the commit; nothing else to undo.
