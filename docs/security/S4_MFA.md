# S4: multi-factor authentication and privileged-account security

## 1. Policy
| Role | MFA | Before enrolment |
|---|---|---|
| ADMIN, DEVELOPER, COMMANDER, OPERATOR, RESCUE_OFFICER | **mandatory** | password login gives a *restricted* session that can only enrol MFA, change a temporary password, view its own profile and sign out. Every operational endpoint answers 403 (`X-MFA-Enrollment-Required`) |
| CITIZEN, VOLUNTEER | optional (self-service on/off, with the password and a recent code) | full access as before; if they turn MFA on, sign-in then needs the second step |
| Guests (not signed in) | never | emergency reporting, report tracking and public information are unchanged |
Existing privileged accounts keep their records, roles and teams; nobody is marked enrolled by the migration. They enter the restricted enrolment flow at their next request.
No SMS factor exists (no provider). There is no universal bypass code and no setting that turns MFA off; the audit action name `MFA_DISABLED` records a public user switching *optional* MFA off.

## 2. Authentication state machine (enforced on the server, `services/auth_state.py`, `api/deps.py`)
```
UNAUTHENTICATED --password OK, MFA enabled--> MFA_CHALLENGE_PENDING (a single-use challenge, NOT a session; 5 min, 5 tries)
        |                                        |  correct TOTP / recovery code -> session with assurance=MFA
        | password OK, MFA off or not enrolled --+-> session with assurance=PASSWORD
        v
   session state, recomputed from the account on EVERY request (first match wins):
     PASSWORD_CHANGE_PENDING      temporary password (break-glass / admin reset)      -> me, me/password, logout
     MFA_ENROLLMENT_PENDING       privileged role, no ACTIVE credential               -> + mfa/status, enroll/start, enroll/confirm
     MFA_CHALLENGE_PENDING        MFA required/enabled but THIS session never did a factor -> me, logout
     CONTACT_VERIFICATION_PENDING optional policy PRIVILEGED_REQUIRE_VERIFIED_EMAIL    -> + verify email, change contact
     AUTHENTICATED                everything else                                      -> all endpoints, then S1 permissions
   SESSION_ENDED                  expired / revoked / replay / password / role / team change -> 401
```
- A password never yields a fully privileged session when MFA is required: an enrolled account gets only a challenge (no cookies, no token); an unenrolled privileged account gets the restricted session above.
- **Refresh cannot upgrade:** the refresh token belongs to a session row whose `assurance` only changes by completing a factor (verify, enrolment confirm, re-auth). Rotation keeps the row, so a PASSWORD session stays PASSWORD (tested through repeated refreshes and for sessions that pre-date enrolment).
- Optional-auth endpoints (reports, uploads, evidence photos) treat any non-AUTHENTICATED session as a guest, so a password-only privileged session cannot read evidence photos.
- Claims in a token (`aal`, `role`, ...) are never used; assurance comes from the database session row.

## 3. TOTP (RFC 6238)
Library: **pyotp 2.9.0** (maintained, small, no dependencies; pinned; `pip-audit` clean) for the algorithm; **segno 1.6.6** (pure Python, no dependencies) to draw the QR as SVG; **cryptography 50.0.2** (AES-GCM; `pip-audit` flagged 47.0.0, 48.0.1 and 49.0.0, so the pin was raised until the audit was clean). HMAC-SHA1, 6 digits, 30 s step (what authenticator apps support). Secrets: 160 random bits (`secrets`). Verified against the RFC 6238 Appendix B vectors for SHA-1/256/512 and an independent RFC 4226 implementation (`tests/test_mfa_totp.py`).
- **Drift:** +/- 1 step (+/- 30 s), hard-capped (the setting can never widen it).
- **Replay:** the newest accepted step is stored; the same or an older step is refused; the update is atomic, so concurrent use has one winner.
- **Enrolment:** `enroll/start` (needs the password again) returns the secret, `otpauth://` URI and QR **once**; nothing is active until `enroll/confirm` with a correct code. Starting again replaces the pending secret. Enrolling ends all other sessions and upgrades only the current one.
- **Rate limits** (shared persistent store): per challenge 5 wrong codes; per account 8 failures/15 min; per address 40 attempts/15 min; recovery-code failures 5/hour; enrolment starts 6/hour; regeneration 5/hour. 401/429 answers are generic.

## 4. Secrets at rest and key management (`services/mfa_crypto.py`)
- TOTP secret = **AES-256-GCM** ciphertext `v1:<key id>:<nonce||ct>`; the user id is authenticated data, so a ciphertext copied to another account fails. Never plaintext in any table (swept in tests).
- Keys come only from the environment: `MFA_ENCRYPTION_KEYS="id:KEY[,id2:KEY2]"` (32 random bytes, base64url; first = encrypting key). Generate with `python scripts/mfa_keys.py generate`. Keep keys in the deployment's secret store, **not** in the database, repository or backups of the database.
- **Production refuses to start** without a valid key (`import app.main` fails); an invalid key is refused everywhere. Development without a key creates a git-ignored `backend/.mfa_key` (0600); production never does.
- **Rotation:** put the new key first (`new:KEY2,old:KEY1`), restart, run `python scripts/mfa_keys.py rotate` (verified backup first), run `check`, later remove the old key.
- **Losing every key:** stored secrets cannot be decrypted. Affected users get a generic "temporarily unavailable" message; `mfa_keys.py check` lists the user ids; each must be reset with `account_admin.py reset-mfa` and re-enrol. Recovery codes are hashed with a different secret (`JWT_SECRET`), so they are not affected by this key but cannot replace TOTP for ordinary use. **Back up the key separately from the database; the database backup alone cannot restore MFA.**
- Never exposed: not in API responses (except the one-time enrolment reply to the authenticated owner), `/auth/me`, status, the user list, diagnostics (counts only), audit entries, logs, the dev outbox or browser storage (tests sweep all of these; the secret lives only in React component state during enrolment).

## 5. Recovery codes
10 codes, 16 symbols (80 bits) each, `secrets`-random, stored only as HMAC-SHA256, shown once at generation with offline-storage instructions, single use with an **atomic** claim (6 concurrent attempts: one winner), tolerant of case/spaces. Regenerating deletes every earlier code (needs a recent factor). Using one never changes the role and never disables MFA; the next sign-in still asks for a factor. Audit entries record counts, never values.

## 6. Sensitive-action re-authentication (`ensure_recent_mfa`, `POST /auth/mfa/reauth`)
A session counts as "recent" when `mfa_at` is within the window; otherwise the API answers 403 with `X-MFA-Reauth-Required`, the UI asks for a code, calls `/auth/mfa/reauth` (replay-protected, rate-limited) and retries. Accounts without MFA are not asked (public users still re-enter their password).
| Action | Window |
|---|---|
| change password, change email/phone, regenerate recovery codes, turn optional MFA off | 10 min (`MFA_FRESH_MINUTES`) |
| privileged account management (create/update user, revoke a user's sessions) | 10 min |
| commander **approval** of a dispatch plan; publishing a **CRITICAL** alert | 5 min (`MFA_APPROVAL_FRESH_MINUTES`) |
Declining a plan and non-critical alerts are unchanged. A stale approval is refused **before** anything changes (the incident stays PENDING_APPROVAL, the team AVAILABLE). All P0 approval/dispatch rules and tests are untouched. No autonomous dispatch and no alert workflow (Phase E) was added.

## 7. Recovery paths never remove MFA
Email password reset, email verification, contact changes, session refresh, administrator password resets (public accounts only, S2) and break-glass **password** recovery do not touch MFA: the next sign-in still needs the second factor (all tested). A reset gives no session. No HTTP route can reset or remove another user's MFA: not for administrators, not for anyone.

## 8. Lost authenticator: host-level, separately authorised (`scripts/account_admin.py reset-mfa`)
Requires shell access to the server (authorised separately from application administrators), `--i-am-authorized`, `--reason`, and `--identity-verified "<how the owner's identity was re-verified>"` (15+ characters, recorded). It takes a verified backup, deletes the credential, pending enrolment, recovery codes and challenges, ends every session, audits `ACCOUNT_CLI_MFA_RESET` (`cli:<os user>`), leaves the password and role unchanged, and the account must **re-enrol before any operational access**.
**Anti-impersonation rule:** for privileged accounts a password recovery (CLI, email link or administrator reset) and an MFA reset must be at least 24 h apart (either order), otherwise exit code 3; a second, different authorised operator may override with `--second-authorizer NAME` (recorded).
**Trust assumptions (honest limits):** the operator with shell access can read/modify the database and could bypass the tool entirely; the tool cannot verify that identity was really checked or that the second authoriser is a different human. The controls are policy, separation (no web route), a time gap, backups and an audit trail to be reviewed. Anyone holding both the database and the encryption key can read TOTP secrets.

## 9. Migration 0005 and behaviour changes
Adds `mfa_credentials`, `mfa_recovery_codes`, `auth_challenges`, and `auth_sessions.assurance/mfa_at/mfa_method`. Existing accounts and sessions are untouched (sessions keep assurance PASSWORD); up/down/up, M0 backup before migration, restore of the pre-migration backup, retained privileged accounts, restricted-before-enrolment and "nobody marked enrolled" are tested. Rollback: restore the backup (or `alembic downgrade 0004`; every enrolment is lost and mandatory-MFA code must not run against it). Changes people will notice: privileged logins, including the seeded demo accounts, enrol at first sign-in; production needs `MFA_ENCRYPTION_KEYS`; a few sensitive actions ask for a fresh code.

## 10. Existing tests that were changed (reasons)
Nothing was weakened; P0 (66), S0 (53), S1 policy/scoping/service/environment suites were not edited.
| File | Change | Reason |
|---|---|---|
| `tests/conftest.py` | `sign_in`/`make_user(mfa=)`/`login_complete`/`enroll_*` helpers; per-run random MFA key; autouse refresh of `mfa_at` | privileged sign-ins now include a second factor; sessions created at collection time would exceed the 5-minute approval window |
| `test_endpoint_authorization.py` + golden | 7 new endpoints | every endpoint needs an explicit decision |
| `test_sessions.py` | `login()` helper completes MFA for privileged roles; allowed column set includes the 3 assurance columns | S2 schema extended; staff need MFA |
| `test_stale_access.py` | helper uses MFA-enrolled staff | staff need MFA to reach the endpoints under test |
| `test_break_glass_hardening.py` | after the forced change the operator must also enrol, then permissions are asserted | S4 makes enrolment mandatory (assertion kept, one step added) |
| `test_password_recovery.py` | two staff tests use MFA-enrolled operators and `login_complete` | a reset must keep MFA; assertions kept |
| `test_environment_guard.py`, `test_session_cookies_production.py`, `test_notifications.py` | pass `MFA_ENCRYPTION_KEYS` to the production subprocess | production refuses to start without a key |
| earlier-run flake | none | (an interrupted run overlapped my own edits; the suite is deterministic when run alone) |

## 11. Remaining risks and limitations
1. A phished or relayed code is accepted until its 30 s step ends (TOTP is not phishing-resistant; WebAuthn is a later option).
2. Whoever has the database **and** the encryption key reads TOTP secrets; whoever has shell access can bypass the tool (section 8).
3. Replay prevention is per credential: two devices cannot use the same step.
4. Recovery codes are the only fallback; users who lose both phone and codes need the host-level procedure.
5. Phone clocks more than ~30 s off fail; the UI says to check the phone's clock.
6. The 5-failure/15-minute and per-account limits can be used to annoy a known username (no existence leak).
7. Optional MFA for public roles is opt-in; many citizens will not enable it.
8. Rate limits are shared per database host only (S3); no Redis/PostgreSQL was added.
9. Demo accounts still exist in development databases (S5) and, in development, share the documented demo password until they enrol.
