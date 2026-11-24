# S5 evidence: production account hardening, invitations, agencies

Throw-away databases; no real mail or SMS; nothing deployed; no personal or laptop database touched.

## Test results at the S5 checkpoint
| Suite | Result |
|---|---|
| Complete backend suite | **757 passed**, 1 skipped (live Ollama) |
| P0 dispatch safety (`test_p0_safety` + `test_team_selection`), files unchanged | 66 passed |
| S0 security (`test_public_media` + `test_public_refs`), files unchanged | 53 passed |
| S5 invitations, activation sequence, waivers, CLI (`test_s5_invitations`) | 28 |
| S5 agencies, metadata-not-boundary, cross-agency coordination (`test_s5_agencies`) | 14 |
| S5 bootstrap, demo-account disabling, repository hygiene, start-up validation (`test_s5_bootstrap_demo_scripts`) | 27 |
| Migrations incl. `0006` up/down/up, backup + restore, no existing row changed (`test_migrations`) | 25 |
| Production/development environment guard (`test_environment_guard`, rewritten, see S5 doc section 11) | 10 |
| Endpoint authorization + permission policy (golden matrices, additions only) | 42 |
| Frontend `npm run build` | passes |
| `pip-audit -r backend/requirements.txt` | no known vulnerabilities |

Previous suites (S1 policy/scoping/service, S2 sessions, S3 recovery, S4 MFA) all pass inside the complete run; their files changed only where
S5 deliberately changed behaviour (listed with reasons in `docs/security/S5_ACCOUNTS_AGENCIES.md` section 11). No assertion was weakened.

## What the tests prove (security-critical)
Expired, revoked and reused invitations are refused with one generic answer; 8 simultaneous acceptances create exactly one account; role,
team, agency and email cannot be injected through the accept request; a new account has no permissions and no operational access until
contact verification then MFA are complete; no web endpoint issues a privileged invitation (administrators cannot self-invite or promote);
public registration cannot create any privileged role; production creates no account, refuses demo seeding and unsafe configuration; the
retired demo password and every demo-credential mechanism are absent from current code, frontend and docs; the demo-disabling tool is a dry
run by default, needs a confirmation phrase, takes a verified backup, revokes sessions, audits, deletes nothing and does not touch real users
who share a demo username; bootstrap cannot be repeated.

Browser evidence for invitation acceptance and the activation restrictions is collected with S6 (`docs/evidence/S6/`).
