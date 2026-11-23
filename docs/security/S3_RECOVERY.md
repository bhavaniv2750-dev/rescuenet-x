# S3: contact verification, password recovery and rate limiting

## 1. Contact verification
| Item | Behaviour |
|---|---|
| Email code | 6 digits from `secrets.randbelow`, valid 10 min, 5 wrong tries then void, resend cooldown 60 s, at most 5 requests per hour per account |
| Storage | `one_time_tokens`: only an **HMAC-SHA256** of `purpose|user|target|code` keyed with the server secret (a 6-digit code has too little entropy for a plain hash). Single use (atomic claim). Bound to the exact address it was issued for |
| Verified flag | `users.email_verified_at` is set **only** when a correct code is entered. Sending a code, or a transport "success", never sets it |
| Changing a contact | `PATCH /auth/me/contact` needs the current password; the changed address/number becomes **unverified**, codes issued for the old address are voided, reset tokens are voided, a verified old address receives a notice, the change is audited without the values |
| Phone | Available only when an SMS provider exists. None is integrated, so `/auth/verify/phone/*` answers 409 "no SMS provider is configured", no code is generated and phones stay unverified |
| One owner per address | Several accounts may hold the same *unverified* address; if another account already proved it, a code cannot verify it for a second account. Registration never reveals that an address is taken; login by email works only when exactly one account has that address |
| Restrictions for unverified contacts | password-reset mail goes only to a verified address; a volunteer who signed up with their own account cannot be verified by a coordinator until they verified an email or phone; login by a shared unverified address is refused. Unverified contacts **never** block signing in or emergency reporting |

## 2. Delivery transports (`services/notifications.py`)
| Transport | When | Status written | What the UI may say |
|---|---|---|---|
| `DEV_OUTBOX` | `RESCUENET_ENV=development` and no SMTP configured | `NOT_DELIVERED_DEV` | "stored in the development outbox; nothing was delivered" |
| `SMTP` | `SMTP_HOST` and `SMTP_FROM` set (password from the environment only) | `ACCEPTED_BY_SMTP` (server accepted; inbox delivery unknown) or `FAILED` | "handed to the mail server; delivery is not guaranteed" |
| `DISABLED` | production without SMTP; all SMS | `DISABLED` | "email/phone verification is not available" (503/409; no code is even generated) |

No status ever means "delivered to the person". The message body (code or link) is stored **only** by the development outbox; recipients are masked in the table; SMTP error text is never logged or returned. `GET /api/dev/outbox` (codes visible) answers 404 unless development **and** the caller is on this machine. `GET /auth/capabilities` is public and lets the UI word messages truthfully; it contains no secrets. Codes are never in public API responses, production logs or the frontend bundle.

## 3. Forgot / reset password
- `POST /auth/password/forgot`: always **202 with the same body** for existing, unknown, unverified and disabled accounts (tested). A link is requested only for an active account with a **verified** address. Rate limited per address and per identifier; if email cannot be sent at all (production without SMTP) it says so (503) because that is a fact about the server, not an account.
- Reset token: 32 random bytes in a link (`/?reset=TOKEN`, removed from the address bar on load), valid 30 min, single use (atomic claim), only its SHA-256 stored, a newer request voids the older link.
- `POST /auth/password/reset`: weak or unchanged passwords are refused **without burning** the token; expired, reused, unknown and malformed tokens get one identical answer; success ends **every** session, clears lockout, voids other reset tokens, audits (`PASSWORD_RESET_REQUESTED/COMPLETED`, no secrets), notifies the verified address, and **does not sign anyone in** (so sign-in rules, and later MFA, still apply).
- **Staff** (any non-public role): email recovery only with a verified address that was **not changed in the last 24 h** (`STAFF_RESET_COOLDOWN_HOURS`), so someone holding a stolen session cannot swap the address and reset at once; staff with no verified address recover only through the host-level tool. A reset never changes a role or grants anything.
- **S4 requirement:** a reset must not disable or bypass MFA; S4 must keep MFA enrolled across resets.

## 4. Break-glass hardening (`backend/scripts/account_admin.py`)
Still host-shell only, `--i-am-authorized` + recorded reason, verified backup, audited as `cli:<os user>`, sessions ended. New: the account is flagged `must_change_password`. Until the owner chooses a new password the API answers **403** (`X-Password-Change-Required: true`) to everything except `/auth/me`, `/auth/me/password`, `/auth/logout(-all)`; `/auth/me` shows `permissions: []`; the UI shows only a "choose your own password" screen. The temporary password cannot be kept (the new one must differ), is only ever stored as a salted PBKDF2 hash (checked against every table), is printed once to the operator's terminal and never logged. Recovery never changes the role, team or active flag (tested for all 7 roles). An administrator's reset of a **public** account sets the same flag. Guest emergency reporting is unaffected.

## 5. Rate limiting (shared and persistent)
Counters are rows in `rate_limit_events` (migration 0004) in the application database, keyed by **keyed hashes** of client address / identifier. Insert-then-count in one transaction means concurrent workers can both refuse a borderline request but never both allow it; counters survive restarts and are shared by every worker that shares the database (tested with real subprocesses).
| Limiter | Default | On store failure |
|---|---|---|
| Login: per address / per supplied username-or-email (failures; identical answer for unknown accounts) | 30 / 5 per 15 min (replaces the old account lock-out) | closed (503) |
| Registration per address | 10 / hour | closed |
| Verification requests per account (+ cooldown 60 s) / confirm attempts per account | 5 / h, 15 / h (+5 per code) | closed |
| Forgot-password per address / per identifier | 5 / 3 per hour | closed |
| Reset attempts per address | 10 / hour | closed |
| Guest reports / uploads / tracking lookups and failures (S0) | 10 / 25 / 60 and 10 per 15 min | **open** (never block someone calling for help) |
Every 429 carries `Retry-After`; emergency-endpoint messages add "call 112".

**Deployment requirements (no new infrastructure was introduced).** The store is the existing database, so it works for any number of worker processes on one host that share the SQLite file (set `busy_timeout`; WAL mode is recommended for several workers). It is **not** enough when the app runs on several machines: that needs a database server (PostgreSQL) or a Redis-backed implementation of the same `rate_limit` interface (`check`, `hits`, `record`, `too_many`, `clear`). Introducing Redis would add a service to run, secure and monitor and a Python dependency, so it was deliberately **not** added; ask before doing so. A reverse proxy should also rate limit at the edge, and `TRUSTED_PROXY_COUNT` must be set correctly behind one.

## Migration 0004
Adds `users.email_verified_at/phone_verified_at/email_changed_at/must_change_password` and tables `one_time_tokens`, `notification_outbox`, `rate_limit_events`. **Nothing existing is marked verified**, no password is forced to change, nobody is signed out. Behaviour changes: login by email now needs a unique address; the account lock-out became the shared limiter (5 failed attempts per 15 min per identifier). Backed up automatically by the M0 tooling; up/down/up tested. Rollback: restore the backup or `alembic downgrade 0003` (pending codes, outbox and counters are lost).

## Remaining risks
1. No real mail was sent in tests: SMTP is verified with a faked server class (accept/failure/credentials/logging), not against a live mail server. Set up and test a real SMTP account before relying on recovery.
2. Email is a single factor: whoever controls a verified mailbox can reset a non-staff password. Staff are protected by the change cool-down and, from S4, MFA must survive resets.
3. The 5-failures/15-min limiter can be used to lock out a known username (denial of service); it does not reveal whether the account exists. Recovery by reset link clears it.
4. Phone verification and SMS are unavailable until a provider is integrated.
5. The dev outbox shows codes to anyone on the local machine in development; never run development mode on a shared host.
6. Rate limiting beyond one host needs the infrastructure described above.
7. Demo accounts and the default demo password still exist in development databases (S5).
