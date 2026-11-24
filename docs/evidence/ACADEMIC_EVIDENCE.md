# Technical evidence summary for the academic submission (S0 to S6)

Purpose: concise, verifiable facts about what the system actually does. It deliberately contains **no** performance figures, flood-prediction accuracy
claims, operational partnerships or real-world deployment claims: none exist. The project report and synopsis are not edited here.

## 1. Actual architecture
* Backend: FastAPI, Pydantic v2, SQLAlchemy, SQLite, Alembic (head `0006`). Frontend: React 19, TypeScript, Vite, Leaflet. Single-server deployment; no Redis,
  PostgreSQL, paid SMS or external identity provider.
* Security layers (each with its own document in `docs/security/`): S1 central role-permission matrix; S2 server-side sessions, rotating refresh tokens, CSRF;
  S3 contact verification, password recovery, shared rate limiting; S4 TOTP multi-factor authentication; S5 production account hardening, invitations, agencies;
  S6 backend-driven workspaces and navigation. P0 dispatch safety and S0 private media/guest tracking are earlier milestones.
* Single source of authorisation: `backend/app/core/permissions.py` (role to permission) and `backend/app/api/deps.py` (guards). Navigation is derived from the
  same permissions (`backend/app/core/navigation.py`) and is a convenience, never the boundary.

## 2. Schema changes (Alembic)
| Revision | Change |
|---|---|
| 0001 | baseline (adoption of the earlier schema) |
| 0002 | public references, media assets |
| 0003 | server-side sessions, refresh tokens |
| 0004 | contact verification, one-time tokens, notification outbox, rate-limit events |
| 0005 | MFA credentials (encrypted), recovery codes (HMAC), challenges, session assurance |
| 0006 | agencies, invitations (hashed tokens), `users.agency_id / contact_verification_required / contact_verification_waived_at / is_demo`, `rescue_teams.agency_id` |
Every revision is tested for upgrade, downgrade/upgrade, automatic pre-migration backup and restore (`backend/tests/test_migrations.py`).

## 3. Authentication and authorisation workflow (as implemented)
Sign-in: password -> (if MFA) single-use challenge -> TOTP or recovery code -> session (15-minute access token bound to a server-side session, rotating
single-use refresh cookie). Account activation for staff: host-issued invitation -> owner password -> emailed code (contact verification) -> mandatory MFA
enrolment -> next sign-in with second factor -> role permissions. Restricted states return no permissions and no navigation and are refused by the API.
Privileged accounts are never created through public registration or by web administrators (S2/S5).

## 4. Agency and invitation workflows
See `docs/security/S5_ACCOUNTS_AGENCIES.md` sections 2 and 8. Agencies are organisational metadata; they do not restrict access (tested, including
cross-agency dispatch coordination). Invitations are single-use, expiring, revocable, bound to recipient email, role, agency and team.

## 5. Role-permission matrix
Generated from code and the golden endpoint matrix: `docs/security/PERMISSION_MATRIX.md` (roles x permissions, and every endpoint x role outcome).
Navigation per role: `backend/tests/golden/navigation_matrix.json`, summarised in `docs/security/S6_WORKSPACES_NAVIGATION.md`.

## 6. API endpoint changes since S4
S5: `/api/invitations/inspect`, `/accept` (public, token required), `/api/invitations` (list), `/{id}/revoke`; `/api/agencies` (list, detail, create, patch),
`/api/agencies/members/{user_id}`, `/api/agencies/teams/{team_id}`; `/api/auth/portals` no longer returns any credential. S6: `/api/auth/workspace` (public),
`workspace` inside `/api/auth/me`. All covered by `test_endpoint_authorization.py` (every endpoint probed as anonymous and as each of the seven roles).

## 7. Verified test counts (S6 checkpoint; throw-away databases)
| Suite | Result |
|---|---|
| Complete backend suite | see `docs/evidence/S6/EVIDENCE.md` (final run) |
| P0 dispatch safety | 66 passed |
| S0 private media and public references | 53 passed |
| S5 tests (invitations 28, agencies 14, scripts/hygiene/start-up 27) | 69 passed |
| S6 workspace and navigation tests | 22 passed |
| Frontend production build | passes |
| `pip-audit` on `backend/requirements.txt` | no known vulnerabilities |

## 8. Screenshots
Sanitized browser evidence (emails and secrets blurred, development database only): `docs/evidence/S6/` (public and professional workspaces per role,
invitation acceptance, restricted activation screens, unauthorized and not-found pages, session revocation, role change, team reassignment, agencies),
`docs/evidence/S4/` (MFA), earlier folders for S0 to S3.

## 9. Implemented versus planned
| Implemented | Not implemented (planned or out of scope) |
|---|---|
| Role/permission matrix with golden tests, sessions, CSRF, rate limits | Hard multi-tenant isolation between agencies |
| Email-code contact verification (development outbox; SMTP code path) | Verified delivery to real mailboxes; SMS/phone verification |
| TOTP MFA with encrypted secrets and recovery codes | Hardware keys / WebAuthn |
| Invitation onboarding, host-authorised bootstrap, demo-account disabling | External identity provider / SSO |
| Backend-driven navigation and minimal path routing | Full frontend redesign (F0 to F2), mobile app, ML retraining, Ollama integration |

## 10. Known limitations
* Everything runs against simulated and public datasets; there is no real emergency-service integration and no real-world deployment.
* A person with shell access to the server remains fully trusted; CLI audit entries are policy and evidence, not cryptographic separation.
* Email delivery and the SMTP path are exercised only against stubs/the development outbox.
* The frontend has no automated browser test suite in the repository; browser checks are scripted evidence runs (`docs/evidence/*/browser_run.txt`).
