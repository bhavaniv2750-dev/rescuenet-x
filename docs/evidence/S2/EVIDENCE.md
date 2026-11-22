# S2 evidence: secure sessions, rotation and revocation

## Test results (isolated throw-away databases; no real alerts, dispatches or deployments)
| Suite | Result |
|---|---|
| Complete backend suite | **435 passed**, 1 skipped (live Ollama) |
| P0 dispatch safety (`test_p0_safety` 48 + `test_team_selection` 18), files unchanged | 66 passed |
| S0 private media / guest refs (`test_public_media` 33 + `test_public_refs` 20), files unchanged | 53 passed |
| S1 permission matrix (`test_permission_policy` 36, `test_endpoint_authorization` 5 (extended), `test_resource_scoping` 37, `test_service_authorization` 23, `test_environment_guard` 7) | all pass; policy/scoping/service/guard files unchanged |
| Session lifecycle (`test_sessions`) | 34 |
| Token rotation, replay, hash-only storage (`test_token_rotation`) | 11 |
| CSRF (`test_csrf`) | 14 |
| Legacy-token invalidation (`test_legacy_tokens`: 7 roles × every protected endpoint) | 12 |
| Production cookie attributes (`test_session_cookies_production`, fresh interpreter each) | 5 |
| No secrets in logs/stdout/audit/errors (`test_token_logging`) | 2 |
| Privileged-account escalation + recovery tool (`test_privileged_escalation`) | 31 |
| Role change / deactivation / team change (`test_stale_access`, rewritten for S2) | 9 |
| Migration 0003 up/down/up, pre-migration backup (`test_migrations`) | 15 total |
| Frontend `npm run build` | passes |
| `pip-audit -r backend/requirements.txt` | no known vulnerabilities |

Tests changed on purpose (they encoded the old rules): `test_auth` (admin-created staff accounts), `test_stale_access` (now 401 instead of 403 after
revocation), `test_endpoint_authorization` + golden (new endpoints; cookie-authenticated ones covered by dedicated suites), `conftest` (high session cap for
the test run, `make_user` helper, developer portal). P0, S0 and the other S1 test files were not edited.

## Legacy-token invalidation evidence
`tests/test_legacy_tokens.py` mints tokens exactly as the pre-S2 code did (HS256, real secret, `sub`/`role`/`iat`/`exp`, 480 min, even 1-minute-old ones) for all
seven demo roles and calls every protected endpoint: all return 401 (`Invalid access token`); a legacy token cannot be exchanged at `/auth/refresh`; guest
reporting with a legacy token still works. Browser: a `rescuenet.token` left in sessionStorage/localStorage is deleted on load and the sign-in page is shown
(`01_login_after_legacy_token_cleared_1366.png`, `browser_run.txt`: `legacy token keys after load: [null,null]`).

## Privileged-account escalation results
Administrator attempts, all **403 + audited, nothing changed**: create COMMANDER / OPERATOR / RESCUE_OFFICER / DEVELOPER / ADMIN accounts (5); reset password of each
of those roles (5), of another admin and of themselves; promote CITIZEN/VOLUNTEER into each privileged role (10); reset-then-promote chain. Afterwards the admin still
gets 403 on assign, approve, triage, alert publish and incident read. Still allowed: create/reset/lateral-change public accounts, deactivate, demote, sign out
everywhere. Host-level recovery tool: refuses without `--i-am-authorized` and a reason, backs up, ends sessions, audits, never prints a hash, and the one-time password is not in
the audit entry.

## Browser run (`browser_run.txt`; backend with a 30-second access token to make renewal observable)
- Login through the UI; cookies: `rn_refresh httpOnly=true path=/api/auth sameSite=Lax` (dev), `rn_csrf` readable; `document.cookie` shows only `rn_csrf`; **sessionStorage/localStorage hold no token**.
- Reload restores the session from the cookie (refresh cookie rotated).
- Over 42 s (longer than the access-token lifetime): 1 automatic refresh (200), 0 responses with 401, still signed in.
- Admin revokes the commander's sessions: the next poll fails, refresh fails, the app returns to the sign-in page (`04_...png`).
- Sign out: refresh cookie gone; `/auth/refresh` afterwards returns 401.
- Screenshots: `01` sign-in after legacy token cleared, `02` signed in after reload, `03` My Account sessions panel, `04` session ended, `05` admin console ("Owner-controlled", no staff password reset), `06` new account dialog (public roles only).

## Not covered / caveats
Production cookie attributes are verified through HTTP headers in tests (fresh interpreter, `https` base URL), not in a real https browser. Multi-tab simultaneous refresh was not stress-tested in a browser (Web Locks serialisation is in place; see risks in `docs/security/S2_SESSIONS.md`).
