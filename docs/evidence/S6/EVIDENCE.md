# S6 evidence: backend-driven workspaces and navigation

Development servers, a fresh throw-away database, simulated fixture accounts, no real mail or SMS, nothing deployed.
Screenshots are sanitized (email addresses and secrets blurred). `browser_run.txt` is the unedited log of the scripted browser run.

## Test results at the final checkpoint
| Suite | Result |
|---|---|
| Complete backend suite | **779 passed**, 1 skipped (live Ollama) |
| P0 dispatch safety (`test_p0_safety` + `test_team_selection`), files unchanged | 66 passed |
| S0 security (`test_public_media` + `test_public_refs`), files unchanged | 53 passed |
| S5 suites (invitations 28, agencies 14, bootstrap/demo scripts/hygiene/start-up 27) | 69 passed |
| S6 workspace and navigation (`test_s6_workspace`) | 22 passed |
| Migrations (incl. `0006` up/down/up, backup + restore) | 25 passed |
| Endpoint authorization + permission policy (goldens: additions only) | 44 passed |
| S1 to S4 suites (policy, scoping, sessions, recovery, MFA, break-glass) | pass inside the complete run |
| Frontend `npm run build` | passes |
| `pip-audit -r backend/requirements.txt` | no known vulnerabilities |

## What `test_s6_workspace.py` proves
Each role receives exactly the navigation the old hard-coded frontend offered (plus the one new "Agencies & Invitations" entry for administrators); a golden
navigation matrix guards it; administrators and developers have no operational entries or capabilities; capabilities derive from permissions only; every entry
offered to a role is backed by an API call that role may make, and entries not offered stay refused by the API; guests get the public workspace with nothing
account-bound; the payload contains ids and booleans only; restricted states (invited, temporary password, MFA pending) get no navigation and list the remaining
activation steps; activation completes into the full workspace; navigation follows the stored role on the very next call; role change, team reassignment and
administrator revocation end sessions and a new sign-in gets the new workspace; a regression test pins the cookie-credentials defect described below.

## Defects found by this work (and fixed)
* **Browser run:** the frontend client did not send credentials for `/invitations/accept`, so the new session's cookies were dropped and a reload signed the new
  owner out. Fixed in `api/client.ts`; regression test `test_every_endpoint_that_starts_a_session_is_called_by_the_frontend_with_credentials`.
* **Test harness:** the test suite honoured a `DATABASE_URL` from the calling shell, so a run started from a shell configured for a demo database would have
  executed against it. `conftest.py` now always uses a throw-away database, upload and backup directory.

## Browser verification (`browser_run.txt`)
Guest (public workspace, direct `/public/alerts`, `/console/*` unauthorized, unknown address not found, emergency report without an account), citizen and volunteer
(public experience; console paths unauthorized), rescue officer, operator, commander, administrator and developer (professional workspaces with their own navigation,
landing pages, address bar following clicks and Back, forbidden console paths unauthorized, "Go to my workspace"), invitation acceptance (token read from the URL
fragment and removed from the address bar, masked recipient, owner-chosen password, contact-verification screen first with no console rendered even when a console
address is opened, operational API call refused with 403, emailed code through the development outbox, then mandatory MFA enrolment, then the operator workspace;
reusing the link returns the generic refusal), role change (stored role changed by the host: reload lands on Unauthorized for the old address, then the
new landing page and navigation), administrator revocation (open browser returns to sign-in), team reassignment (officer's session ended, new team shown after
sign-in), agencies and invitations management.

Screenshots: `01` to `04` guest, `05` to `07` citizen/volunteer, `08` to `12` the five professional roles (workspace and an unauthorized direct navigation each),
`13` invitation, `14` and `15` restricted activation, `16`/`16a` activated operator, `17` role change, `18` revoked session, `19` team reassignment, `20`/`21` agencies.
