# S3 evidence: contact verification, password recovery, rate limiting

## Test results (throw-away databases; no real mail or SMS was sent, nothing deployed)
| Suite | Result |
|---|---|
| Complete backend suite | **551 passed**, 1 skipped (live Ollama) (final run after all code changes: 551 passed, 1 skipped; P0 66, S0 53) |
| P0 dispatch safety (66), S0 media/refs (53), S1 policy/scoping/service/environment (103), S2 sessions/rotation/CSRF/legacy/escalation | all pass; P0, S0 and S1 test files not edited |
| Contact verification (`test_contact_verification`) | 27 |
| Notification transports, honest status, no leakage, production behaviour (`test_notifications`) | 13 |
| Password recovery (`test_password_recovery`) | 26 |
| Break-glass hardening (`test_break_glass_hardening`) | 29 |
| Rate limits incl. cross-process sharing and fail-open/closed (`test_rate_limits`) | 19 |
| Migrations incl. 0004 up/down/up (`test_migrations`) | 17 |
| S1/S2 suites adapted: `test_endpoint_authorization` (+11 endpoints, golden regenerated), `test_resource_scoping` (one assertion), `test_auth` earlier | pass |
| Frontend `npm run build` | passes |
| `pip-audit -r backend/requirements.txt` | no known vulnerabilities (no dependency added) |

## Browser run (`browser_run.txt`, development server, fresh database)
Verification: wrong code refused; correct code from the **dev outbox** (labelled "nothing was delivered") verifies; status persists. Forgot password: identical text for a real and a non-existent account; reset link opened, token removed from the address bar, password changed; reusing the link is refused; sign in with the new password works. Break-glass: CLI-created operator signs in with the temporary password and sees only the forced-change screen; reusing the temporary password is refused; after choosing a password the operator workspace opens.
Screenshots: `01` contact unverified, `02` code in dev outbox + honest message, `03` verified, `04` forgot-password answer, `05` reset page, `06` reused link refused, `07` forced change, `08` operator after change.

## Not covered
No live SMTP server was used (a fake SMTP class covers accept, failure, credentials and logging). Phone/SMS flows are unavailable by design. Cross-host rate limiting is not provided (see S3_RECOVERY.md).
