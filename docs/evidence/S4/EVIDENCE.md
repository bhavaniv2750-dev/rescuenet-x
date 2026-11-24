# S4 evidence: TOTP MFA and privileged-account security

## Test results (throw-away databases; no real mail/SMS; nothing deployed)
| Suite | Result |
|---|---|
| Complete backend suite | **680 passed**, 1 skipped (live Ollama) |
| P0 dispatch safety (`test_p0_safety` 48 + `test_team_selection` 18), files unchanged | 66 passed (with real MFA sign-ins for commander/operator) |
| S0 security (`test_public_media` 33 + `test_public_refs` 20), files unchanged | 53 passed |
| S1 policy/scoping/service/environment suites, files unchanged | pass |
| `test_endpoint_authorization` (+7 endpoints, golden regenerated) | 5 |
| RFC 6238 vectors, drift, replay, secret generation, URI/QR, AES-GCM encryption, key rotation/validation (`test_mfa_totp`) | 31 |
| Enrolment, challenge, expiry/reuse/concurrency, rate limits, recovery codes, state enforcement, bypass attempts, mandatory/optional by role (`test_mfa_flows`) | 47 |
| MFA vs password reset/contact/admin reset/break-glass, host-level MFA reset, key tool, re-authentication, state table, production start-up, secrets hygiene, emergency limits without the limiter store (`test_mfa_integration`) | 47 |
| Migrations incl. 0005 up/down/up, backup+restore, retained privileged accounts, restricted-before-enrolment (`test_migrations`) | 21 |
| Frontend `npm run build` | passes |
| `pip-audit -r backend/requirements.txt` | no known vulnerabilities (new pins: pyotp 2.9.0, segno 1.6.6, cryptography 50.0.2) |

## Defects found and fixed while building S4
- `/auth/mfa/verify` returned a new response object and dropped the session cookies (found by the adapted S2 cookie test).
- Non-ASCII input to a code check made `hmac.compare_digest` raise (HTTP 500): input format is now validated first (test `test_malformed_codes_never_match`).
- The rate-limit write could block behind the request's own open write transaction, silently losing a count: the transaction is now released first.
- `pip-audit` flagged three consecutive `cryptography` versions; the pin was raised to a clean release.

## Browser verification (`browser_run.txt`; development server, fresh database, 30-second access tokens)
Commander, operator, rescue officer, administrator and developer each landed on the **enrolment screen first, with no operational navigation rendered**; a password-only API session for administrator and developer got 403 on `/teams`, `/diagnostics`, `/auth/users` and `/incidents`. Each enrolled through the UI (QR/manual key, confirm, recovery codes) and then reached their workspace. Commander: sign-out/in with a code, wrong code refused, refresh cookie rotated after the access token lifetime and the session stayed operational, a second device signed out by "Sign out everywhere", recovery-code sign-in (codes left 10 -> 9), reuse of the same code refused. Citizen: password-only sign-in (MFA optional), opt-in enrolment, password reset by emailed link, then the sign-in **still asked for a code**. Anonymous visitors saw the sign-in page and a guest could report an emergency without any authentication.
Screenshots (secrets, QR codes, recovery codes and tracking codes are blurred; the one screenshot that showed a typed recovery code was removed): `01`-`19` in this folder.

## Not covered
No authenticator *app* was used (codes were computed from the displayed key with an independent TOTP implementation); QR scanning was not exercised. Production cookie behaviour over real https and multi-worker/multi-host behaviour are not tested. See `docs/security/S4_MFA.md` for the limits and trust assumptions.
