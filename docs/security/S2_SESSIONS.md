# S2: secure sessions, token rotation and revocation

## Architecture
```
Browser                                   API (FastAPI)                         Database
  |  POST /auth/login (+remember) ------->  verify password, lockout rules
  |                                         create auth_sessions row  --------->  auth_sessions (id, user_id, expires_at,
  |  <-- JSON: access token (15 min, in memory)                                   idle_timeout_s, revoked_at, user_agent,
  |  <-- Set-Cookie rn_refresh (HttpOnly, path /api/auth)                          client_hash = keyed hash, no raw IP)
  |  <-- Set-Cookie rn_csrf (readable, for the double-submit header)             refresh_tokens (session_id, SHA-256 only,
  |                                                                                used_at, expires_at)
  |  any API call: Authorization: Bearer <access>
  |        -> signature/exp/typ -> session row live? -> user active? -> token_version equal? -> then S1 permission checks
  |           (role, team and assignments are read from the database on every request)
  |  POST /auth/refresh (cookie + X-CSRF-Token) -> mark token used, issue NEW refresh token + access token
  |  presenting a USED refresh token again (replay) -> session revoked, audit SESSION_REPLAY_DETECTED
```
- **Access token**: JWT HS256, 15 minutes (hard cap 60 whatever the setting). Claims: `typ=access`, `sub`, `sid`, `tv`, `jti`, `iat`, `exp`. No role, no permissions.
- **Refresh token**: 32 random bytes (`secrets.token_urlsafe`), single use, only its SHA-256 is stored. Lives only in an HttpOnly cookie. It is never in a response body, never in localStorage/sessionStorage, never logged.
- **Session**: absolute limit 12 h and idle limit 60 min (staff, admin, developer always; "keep me signed in" applies to citizens/volunteers only: 7 days / 24 h idle). At most 10 sessions per account; the oldest is revoked beyond that. Old ended sessions are purged after 30 days.
- **Cookies**: refresh `HttpOnly; Path=/api/auth`; both cookies `Secure; SameSite=Strict` in production, `SameSite=Lax` without `Secure` only when `RESCUENET_ENV=development` (plain http). There is no switch to relax this in production; unset environment means production. Design assumes same-origin deployment behind a reverse proxy (do not deploy publicly yet).
- **CSRF** (refresh and cookie-based logout are the only cookie-authenticated, state-changing endpoints): (1) an `Origin` header, when present, must be same-origin, in `TRUSTED_ORIGINS`, or (development only) a local Vite port; (2) `X-CSRF-Token` must equal the `rn_csrf` cookie AND `HMAC(server secret, session id)`, so a planted cookie or another session's value is useless. Every other endpoint needs the `Authorization` header, which a cross-site page cannot add; cookies alone get 401 there (tested). A failed CSRF check returns 403 without clearing cookies, so a forged request cannot sign anyone out. CORS allows only the configured origins.
- **Revocation** (`revoke_all_sessions`: ends every session and bumps `users.token_version`): password change (self or admin reset of a public account), account deactivation, role change, rescue-officer team change, admin "sign out everywhere", logout-all, CLI recovery. After a self-service password change a fresh session is started for the device used.
- **Emergency reporting**: optional-auth endpoints treat a missing, expired, revoked or invalid token as a guest, so a stale login can never block a report. Guest tracking is unchanged.

## Endpoints
`POST /auth/login`, `/auth/register` (start a session), `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/logout-all`, `GET /auth/sessions`, `DELETE /auth/sessions/{id}` (own sessions only), `POST /auth/me/password` (ends all sessions, starts a new one), admin `POST /auth/users/{id}/revoke-sessions`.

## Legacy-token migration (no grace period)
Before S2 every sign-in produced a 480-minute JWT (`sub`, `role`, `iat`, `exp`) with no server record. The new code accepts only tokens with `typ=access`, a `sid` and a `tv`; **a pre-S2 token fails validation on its first use after deployment, on every authenticated endpoint, for every role, even with a valid signature and unexpired** (`tests/test_legacy_tokens.py`, 7 roles × 40+ endpoints). Nothing converts old tokens, there is no allow-list and no timer. Everyone signs in once. The frontend also deletes any token the old version left in browser storage. Optional-auth endpoints (emergency reporting) keep working for those users as guests. Database: migration `0003` adds `auth_sessions`, `refresh_tokens`, `users.token_version` (default 0) and `users.password_changed_at`; existing users and passwords are untouched; no sessions exist yet, which is what forces the re-login. M0 tooling backs the database up automatically before the migration; `0003` has up/down/up tests. Rollback: restore the pre-migration backup together with the previous code (old-format tokens would become valid again under the old code, so rolling back should be followed by a secret rotation: change `JWT_SECRET`).

## Closing the administrator privilege-escalation paths
S1 found that an administrator could create staff accounts and reset their passwords, gaining that authority indirectly. Audited paths and result:
| Path | Result |
|---|---|
| `POST /auth/users` with a staff/admin/developer role and an admin-chosen password | **403**, audited (`ADMIN_PRIVILEGED_ACCOUNT_CREATE_DENIED`). Administrators create citizen and volunteer accounts only |
| `PATCH /auth/users/{id}` `new_password` on any non-public account (including other admins and themselves) | **403**, audited. Owners change their own password at `/auth/me/password` |
| Promoting an account into a staff/admin/developer role (including "reset a citizen's password, then promote") | **403**, audited. Role changes are possible only to citizen/volunteer (demotion) |
| Reactivation, deactivation, demotion, "sign out everywhere" | allowed (they reduce or contain access); sessions end; audited |
| `GET /auth/team-options` | squad id and name only |
Owner-controlled invitation and recovery for privileged accounts need S3 (verified contact, reset tokens), S4 (MFA) and S5 (invitations), so the unsafe operations are **disabled** rather than left exploitable.

**Separately authorised recovery and provisioning:** `backend/scripts/account_admin.py` (host shell access, not reachable from the web app, therefore authorised separately from application administrators). Needs `--i-am-authorized` and a recorded `--reason`; takes a verified database backup; generates a random one-time password printed once to that terminal and stored nowhere in clear; ends the account's sessions; audits as `cli:<os user>` (`ACCOUNT_CLI_CREATED` / `ACCOUNT_CLI_PASSWORD_RESET`). Provisioning the first administrator in production also uses it.

## Tests (details in docs/evidence/S2/EVIDENCE.md)
Sessions lifecycle (34), rotation/replay/hash-only storage (11), CSRF (14), legacy tokens (12), production cookie attributes (5), no-secrets-in-logs (2), privileged escalation incl. recovery tool (31), session migration (3, inside test_migrations), stale access (9), plus the existing P0, S0 and S1 suites.

## Remaining risks and limitations
1. **Break-glass password is seen by the host operator** who runs the tool, and the account owner is not forced to change it at first sign-in (no `must_change_password` yet). Mitigated by audit, out-of-band hand-over and S3/S5.
2. **No MFA, verified contact or password recovery yet** (S3/S4). Stolen passwords still work until then; replay/revocation protects tokens, not credentials.
3. **Compromise window**: a stolen access token works for up to 15 minutes unless the session is revoked (revocation is checked on every request, so revoked sessions fail at once). A stolen *unused* refresh cookie can be used until the owner refreshes first, after which replay detection ends the session (this is the designed outcome).
4. **Replay detection is strict**: two simultaneous refreshes with the same cookie (two tabs at the same instant) look like theft and end the session. The frontend serialises refreshes across tabs with Web Locks; browsers without Web Locks can still race, at worst causing a re-login.
5. **Development transport is http** (`SameSite=Lax`, no `Secure`); dev needs app and API on the same host name (127.0.0.1 or localhost, not mixed).
6. **Same-origin reverse-proxy deployment is assumed**; configure `TRUSTED_ORIGINS` for anything else. Public deployment is not authorised yet.
7. Rate limiting on refresh and login beyond the existing per-account lockout is not added (S3 adds general limits).
8. Seeded demo accounts and the documented demo password still exist in development databases (S5).
