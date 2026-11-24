# S5: production account hardening, invitations and agencies

Status: implemented on branch `extra-features`. Test counts and evidence are in `docs/evidence/S5/`.
Scope boundary: no Redis, PostgreSQL, paid SMS or external identity provider was introduced. Email delivery depends on an SMTP server the
operator supplies; this project has **not** verified delivery to a real mailbox.

## 1. What changed, in one table

| Concern | Before S5 | After S5 |
|---|---|---|
| Demo accounts | seeded by default with a published password; an `admin` with a generated password was created in production | seeded **only** when `RESCUENET_ENV=development` **and** `SEED_DEMO_USERS=true` (default off), never in production (production refuses to start with the flag on), random or operator-chosen password, flagged `is_demo` |
| Demo password | literal default in config, README, `.env.example`, sign-in page chips, `/auth/portals` response | removed from code, frontend, docs and API; no default exists |
| First administrator | auto-created, `RESCUENET_ADMIN_PASSWORD` or file `backend/.admin_password` | `scripts/bootstrap_admin.py` (host shell access, explicit authorisation, one time, random one-time password) |
| Staff onboarding | host `create` with a random password handed over | **invitations**: owner chooses the password; recipient email bound; contact verification then MFA before any access |
| Agencies | none | metadata table + admin management (not a security boundary) |
| Production start-up | JWT secret auto-generated, localhost CORS always on, demo seeding silently ignored | `startup_checks.py`: fatal for unsafe production configuration, honest warnings |
| Existing demo accounts in old databases | remain active | `scripts/disable_demo_accounts.py` (dry run, backup, confirmation phrase, session revocation, audit, no deletion) |

## 2. Invitation architecture

```
host operator (shell on the server)             recipient                       server
 account_admin.py invite --email --role ...        |                               |
   -> row in `invitations` (SHA-256 of token)      |                               |
   -> one-time link printed ONCE  ---out of band-->|  /#invite=TOKEN               |
                                                   |  POST /api/invitations/inspect  (generic 404 unless usable)
                                                   |  POST /api/invitations/accept   (owner chooses username+password)
                                                   |        one transaction: conditional UPDATE claims the invitation
                                                   |        (used_at IS NULL AND revoked_at IS NULL AND expires_at > now)
                                                   |        then INSERT user (role/agency/team/email from the invitation ONLY)
                                                   v
   restricted session: CONTACT_VERIFICATION_PENDING -> (code to the invited address) -> MFA_ENROLLMENT_PENDING
        -> (authenticator enrolled) -> next sign-in needs the second factor -> AUTHENTICATED -> role permissions
```

* **Token**: 256-bit random (`secrets.token_urlsafe(32)`), shown once, only the SHA-256 is stored. It travels in the URL **fragment**
  (`/#invite=...`), which browsers do not send to servers, so it stays out of access logs; the page removes it from the address bar.
* **Single use**: one conditional `UPDATE ... WHERE used_at IS NULL ...` claims the invitation inside the same transaction that creates
  the account. A concurrent second acceptance matches zero rows. Verified with 8 simultaneous requests (exactly one account).
  A taken username or a weak password rolls the transaction back, so it does not burn the invitation.
* **Expiry**: `INVITATION_HOURS` (default 72, 1 to 168, the CLI `--hours` is capped the same way).
* **Binding**: recipient email, role, optional agency and (for rescue officers) team are fixed at issue time. The accept request is
  never trusted for them: extra fields (`role`, `email`, `team_id`, `agency_id`) are ignored (test).
* **Revocation**: host CLI (`revoke-invitation`) or an administrator (`POST /api/invitations/{id}/revoke`, recent MFA). Revoking a used
  invitation does nothing.
* **Generic failures**: unknown, expired, revoked, used and raced invitations all answer the identical 404 body.
* **Audit**: `INVITATION_ISSUED`, `INVITATION_ACCEPTED`, `PRIVILEGED_ACCOUNT_ACTIVATED_PENDING`, `INVITATION_REVOKED`; no tokens or passwords.
* **Rate limits**: per-address limits on inspect and accept (shared database limiter, fail-closed like other auth endpoints).

### Why issuing is host-only (separation of duties)
No web endpoint issues a privileged invitation. An administrator can list and revoke, but cannot create operational authority for
themselves or anyone else: no self-invite, no promotion, no password choice for others (S2 rules remain). Whoever holds shell access
to the server is authorised separately from application administrators. Even a stolen invitation link does not yield access: the
account stays restricted until a code **sent to the invited mailbox** is entered, then MFA is enrolled.

### Honest limits
* With no email provider the code cannot be delivered. The sign-in screen says so, and a host operator may record a **waiver** for that
  one account (`account_admin.py waive-contact-verification`, audited). A waiver never marks an address verified and never touches MFA.
* Mailbox proof is only as strong as the mailbox. This is not identity proofing of the person.

## 3. Activation sequence (state machine, `app/services/auth_state.py`)

| Order | State | Condition |
|---|---|---|
| 1 | `PASSWORD_CHANGE_PENDING` | temporary password (host `create`, `reset-password`, bootstrap) |
| 2 | `CONTACT_VERIFICATION_PENDING` | contact verification required, address unverified, no MFA enrolled yet |
| 3 | `MFA_ENROLLMENT_PENDING` | privileged role with no active TOTP credential |
| 4 | `MFA_CHALLENGE_PENDING` | this session never completed a second factor |
| 5 | `CONTACT_VERIFICATION_PENDING` | same requirement for an account that already has MFA |
| 6 | `AUTHENTICATED` | permissions of the role apply |

"Contact verification required" = the account is flagged (every invited, bootstrapped or host-created privileged account) **or** the
policy `PRIVILEGED_REQUIRE_VERIFIED_EMAIL` applies to a privileged role (default **on in production, off in development**), unless a
host waiver exists. `/auth/me` returns **no permissions** in any state but `AUTHENTICATED`, and the API refuses everything outside a
short allow-list (unchanged S4 mechanism). Citizens and volunteers are unaffected.

## 4. Existing accounts (migration and recovery path)

Migration `0006` changes **no** existing row, marks nothing verified, flags nobody as demo, and adds nothing to anyone's permissions.
What an existing privileged account experiences after upgrading, per configuration:

| Environment | Policy default | What happens | Recovery |
|---|---|---|---|
| development | off | no change | none needed |
| production, email provider configured | on | account is held in `CONTACT_VERIFICATION_PENDING`; the owner adds/confirms an address and enters the code | self-service |
| production, no email provider | on | held in `CONTACT_VERIFICATION_PENDING`; the screen says email is unavailable | host operator: `account_admin.py waive-contact-verification --username ... --reason ...` (audited), or set `PRIVILEGED_REQUIRE_VERIFIED_EMAIL=false` knowingly |

Existing accounts still must enrol MFA (S4). Existing sessions are not ended by the migration.

### Disabling demo accounts that already exist in a database
`scripts/disable_demo_accounts.py` (run on the server that owns the database; the cloud development environment never touches anyone's laptop database).

```
python scripts/disable_demo_accounts.py                                  # dry run: lists, changes nothing
python scripts/disable_demo_accounts.py --apply --confirm "DISABLE DEMO ACCOUNTS" --reason "go-live" --i-am-authorized
```
Recognition never relies on a username alone: `is_demo = true`, **or** username + full name + email + role all equal the values the old
seeder wrote, **or** (optional `--also-check-password`, hidden prompt) the account signs in with a password you supply. Accounts that merely
resemble a demo username are listed as `NOT TOUCHED`. Applying takes and verifies a backup, deactivates the accounts, flags them `is_demo`,
revokes their sessions, audits each one and **deletes nothing**. It refuses to leave the deployment without an active administrator unless
`--allow-no-admin` is given (then use `bootstrap_admin.py`). A backup restores through the existing `backup` tooling (see S0/M0 docs).

## 5. First-administrator bootstrap

Linux/macOS:
```
cd backend
python scripts/bootstrap_admin.py --username firstadmin --full-name "Name" --email name@example.org --reason "initial deployment" --i-am-authorized
```
Windows (PowerShell):
```
cd backend
python scripts\bootstrap_admin.py --username firstadmin --full-name "Name" --email name@example.org --reason "initial deployment" --i-am-authorized
```
No default password, no endpoint, explicit authorisation flag and reason, verified backup first, random one-time password printed once,
forced password change, mandatory MFA, contact verification, audit (`FIRST_ADMIN_BOOTSTRAPPED`). It refuses (exit 3) while any active
**non-demo** administrator exists, so it cannot be repeated to add or replace an administrator. If MFA is lost afterwards use
`account_admin.py reset-mfa` (S4).

## 6. Production credential safeguards (audit result)

Audit of the current tree found and removed: default `DEMO_USER_PASSWORD`, `RESCUENET_ADMIN_PASSWORD` and the `.admin_password` file,
the `demo_password` and demo-account list in `/auth/portals`, the sign-in-page demo chips and "Tap one to fill" text, the
production auto-created admin, README and `.env.example` credential lines, and the diagnostics check that tested the demo password.
Source scans in `tests/test_s5_bootstrap_demo_scripts.py` fail if the retired password or any of these mechanisms returns.

**Git history is not rewritten.** The retired demo password and the earlier credential defaults remain readable in earlier commits and
must be treated as **permanently compromised**: never reuse them, and disable any account that still has them (section 4).
Fixtures are the only remaining demo mechanism: explicit, development-only, flagged, labelled "(Demo)" / simulated, per-run or
operator-chosen password, impossible to enable in production.

## 7. Start-up validation (`app/services/startup_checks.py`, `scripts/check_config.py`)

FATAL in production (the server refuses to start; development reports the same as warnings where it makes sense): JWT secret shorter than 32
characters, invalid or missing MFA keys, `SEED_DEMO_USERS` on, `DEMO_USER_PASSWORD` set, a localhost CORS origin, empty `DATABASE_URL`,
`INVITATION_HOURS` outside 1 to 168, the development email outbox active. WARNING: no email provider (reported as **unavailable**), SMTP
configured (reported as **not verified by this check**), privileged verification required but email unavailable, `PUBLIC_APP_URL` not an
https address, SQLite single-node limitation. Cookie security is `Secure` automatically in production. Messages never include secret values.
CORS: localhost origins and the regex are development-only; production allows only `CORS_ORIGINS_PRODUCTION`.

## 8. Agencies: metadata versus security boundary

Fields: id, name (unique), type, region, active flag, created/updated timestamps, creator; personnel membership (`users.agency_id`) and squad
association (`rescue_teams.agency_id`). Types are generic categories only (`DISASTER_RESPONSE`, `FIRE_EMERGENCY`, `MEDICAL_RESPONSE`,
`CIVIL_ADMINISTRATION`, `VOLUNTEER_ORGANIZATION`); no real organisation or affiliation is implied and none is seeded.

**Agency is descriptive metadata, not an access boundary.** Permissions come only from roles. Incidents, squads and alerts are not filtered by
agency, and a commander or operator can coordinate squads of any agency during an emergency (tested). Changing an agency changes neither role,
team nor permissions, so it does not end sessions. Inactive agencies cannot receive new people or squads. Management needs `agency.manage`
(administrators only, recent MFA, audited); `agency.view` is held by administrators, commanders and operators. If a hard tenant boundary is
ever required it would need backend filtering on every resource and cross-agency tests; that is **not** implemented.

## 9. Schema (revision `0006`, parent `0005`)
`agencies`, `invitations` (hash only); `users.agency_id`, `users.contact_verification_required`, `users.contact_verification_waived_at`,
`users.is_demo`; `rescue_teams.agency_id`. Downgrade drops them (agencies, invitations, memberships and flags are lost; accounts and
operational records remain). Tested: upgrade, down/up, automatic pre-migration backup and restore, no existing row changed, no schema drift.

## 10. API changes
| Endpoint | Access |
|---|---|
| `POST /api/invitations/inspect`, `POST /api/invitations/accept` | public, single-use token required |
| `GET /api/invitations`, `POST /api/invitations/{id}/revoke` | administrators (revoke needs recent MFA) |
| `GET /api/agencies`, `GET /api/agencies/{id}` | administrators, commanders, operators |
| `POST /api/agencies`, `PATCH /api/agencies/{id}`, `PUT /api/agencies/members/{user_id}`, `PUT /api/agencies/teams/{team_id}` | administrators (recent MFA) |
| `GET /api/auth/portals` | no longer returns `demo_accounts` or `demo_password` |
| `GET /api/auth/me` | adds `agency_id` |

## 11. Changed existing tests (and why; no assertion was weakened)
* `test_environment_guard.py` rewritten: production now creates **no** account (was: exactly one `admin`), refuses to start with demo seeding
  (was: silently ignored), development creates accounts only when explicitly enabled and with no built-in password.
* `conftest.py` and `test_auth.py`: demo accounts use a fresh random per-run password instead of the removed literal; the diagnostics warning
  assertion now matches the flagged-fixture message.
* `test_mfa_integration.py`, `test_session_cookies_production.py`, `test_notifications.py`: production subprocess tests inserted their administrator
  through `RESCUENET_ADMIN_PASSWORD`; they now insert it directly (helper `with_prod_admin`) and use a 48-character JWT secret (production requires 32+).
  One MFA test sets `PRIVILEGED_REQUIRE_VERIFIED_EMAIL=false` explicitly so it still tests the MFA step in isolation, and a new test covers the new order.
* `test_break_glass_hardening.py`, `test_privileged_escalation.py`, `test_mfa_integration.py`: host `create` of a privileged account now needs `--email`; the
  activation test gained the contact-verification step that now precedes MFA enrolment.
* `test_endpoint_authorization.py` and golden matrices: new endpoints added; the golden diffs are additions only.

## 12. Known limitations
* Delivery of invitation or verification email to a real mailbox is not verified by this project (only the development outbox is exercised).
* A person with shell access to the server remains fully trusted; the CLI audit trail is policy and evidence, not cryptographic separation.
* Agency has no enforcement role. Phone verification is unavailable (no SMS provider).
* The migration cannot tell which existing accounts are demo accounts without the fingerprint or password check described in section 4.
