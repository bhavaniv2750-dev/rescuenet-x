# S6: backend-driven workspaces and navigation

Status: implemented on branch `extra-features`. Evidence: `docs/evidence/S6/` (tests, sanitized screenshots, browser log).
Principle: **navigation is a convenience, the API is the boundary.** The server decides what exists for a caller; the frontend renders
exactly that. Every API request is still authorised on its own (`tests/test_endpoint_authorization.py`).

## 1. Where the decision lives
`backend/app/core/navigation.py` holds the single catalogue of entries, each with the permission(s) it needs, and derives everything from
**permissions** (`app/core/permissions.py`) and the **authentication state** (`app/services/auth_state.py`), never from a role name. The old
frontend rules (`navFor`, `isStaff`, `isDepartment`, `canApprove`, `homePage`) were deleted from `frontend/src/auth/access.ts`; `App.tsx`
asks `can(workspace, 'capability')` and `navSections(workspace)` instead.

## 2. Endpoints
| Endpoint | Access | Content |
|---|---|---|
| `GET /api/auth/me` | signed in (any state) | existing profile plus `workspace` |
| `GET /api/auth/workspace` | public | guests get the public workspace; an AUTHENTICATED session gets its own; restricted or dead sessions are treated as guests |

`workspace` contains **only identifiers and booleans**: `experience`, `authenticated`, `activation` (state, restricted reason, remaining
steps), `assurance` (level `NONE|PASSWORD|MFA`, MFA enabled/required, recent MFA), `agency_id`, `team_id`, `capabilities` (derived booleans),
`navigation` (sections, ids, home), `known_paths`. No names, emails, incidents, evidence or credentials (tested).

## 3. Two experiences
* **PUBLIC**: guests, citizens, volunteers. Flood information, reporting; citizens and volunteers add My Reports and My Account.
* **PROFESSIONAL**: rescue officers, operators, commanders, administrators, developers. Membership grants **no** authority: every entry needs its own
  permission. Administrators get identity/system responsibilities only (Admin Console, Agencies & Invitations, Audit Log, Diagnostics, Settings, plus
  information pages); developers get Diagnostics, Data & Models and My Account only. Neither gets Overview, Rescue Operations, AI Supervisor, incidents,
  volunteers, records or dispatch/alert controls (tested against the previous hard-coded behaviour, `tests/test_s6_workspace.py`).

Role to navigation (derived; golden file `tests/golden/navigation_matrix.json`):

| Role | Landing | Entries |
|---|---|---|
| Guest | `/` | Home, Flood Digital Twin, Flood Forecasting, Emergency Alerts, Facilities & Shelters, Report Emergency |
| Citizen, Volunteer | `/` | guest entries + My Reports, My Account |
| Rescue officer | `/console/missions` | My Missions, Emergency Alerts, Flood Digital Twin, Flood Forecasting, Facilities & Shelters, Rescue Records, Report Emergency, My Account |
| Operator | `/console/overview` | Overview, Rescue Operations, AI Supervisor, Emergency Alerts, Flood Digital Twin, Flood Forecasting, Data & Models, Volunteer Coordination, Facilities & Shelters, Rescue Records, Incident Reports, My Account |
| Commander | `/console/overview` | operator entries + Audit Log |
| Administrator | `/console/admin` | Emergency Alerts, Flood Forecasting, Data & Models, Facilities & Shelters, Admin Console, Agencies & Invitations, Audit Log, Diagnostics, Settings, My Account |
| Developer | `/console/diagnostics` | Data & Models, Diagnostics, My Account |

The only entry S6 adds to any role is **Agencies & Invitations** (administrators); all others reproduce the previous behaviour.

## 4. Activation and restricted states
Only an AUTHENTICATED session receives navigation. In any restricted state (`PASSWORD_CHANGE_PENDING`, `CONTACT_VERIFICATION_PENDING`,
`MFA_ENROLLMENT_PENDING`, `MFA_CHALLENGE_PENDING`) `navigation.sections` is empty, `capabilities` are all false, `activation.remaining_steps` lists what is
left (for example `VERIFY_CONTACT`, `ENROLL_MFA`), and the frontend shows the matching screen **before** rendering any page, so a direct address such as
`/console/operations` still shows the verification screen. The API refuses operational calls in these states (S4/S5 mechanism).

## 5. Route architecture (preparation for F2; no redesign)
Path routing is a few lines over `history.pushState`, no router dependency.

| Namespace | Paths | Notes |
|---|---|---|
| public | `/` (home), `/public/<page>` | opens without an account (`/public/*` enters guest mode) |
| professional | `/console/<page>` | requires the entry in the caller's workspace |
| shared | `/account`, sign-in (login page), invitation `/#invite=TOKEN`, reset `/?reset=TOKEN` | the two query/fragment links are preserved exactly |
| problems | Unauthorized (known path, not offered to this caller), Not found (unknown path) | never reveal what a forbidden page holds |

`known_paths` (all catalogue paths) lets the client tell Unauthorized from Not found without hard-coding routes. A signed-out visitor opening a console path
meets the sign-in page first; after sign-in the same address resolves against the new workspace. Back/forward work. Signing out returns the address bar to `/`.
Existing page names and bookmarks (`/`) keep working. **Nothing from F0, F1 or F2 was started.**

## 6. No flash of unauthorised navigation
A signed-in user's workspace arrives inside the same response as the user (login, refresh, `/auth/me`), a guest's is fetched, and until it is known the app shows
a spinner and **no** navigation. The workspace is refreshed every 30 seconds while signed in.

## 7. Live changes
* Role, team change, deactivation, password change, administrator "end sessions": the S2 mechanism ends every session; the next request returns 401 and the
  app returns to sign-in; a new sign-in gets the new workspace (tested and seen in the browser).
* If a stored role changes without ending sessions (a host operation), the very next `/auth/me` / `/auth/workspace` answer reflects it because it is derived
  live from the database (tested).
* Agency membership is metadata: it changes the `agency_id` shown, nothing else.

## 8. Endpoint matrix
`GET /api/auth/workspace` (public) was added to `tests/test_endpoint_authorization.py`; goldens regenerated (additions only); `docs/security/PERMISSION_MATRIX.md`
regenerated. No existing assertion was changed or weakened in S6.

## 9. Known limitations
* The frontend still contains page components keyed by page name; the server decides which names are offered, but not what a page renders (the API decides what
  data each call returns).
* Path routing is deliberately minimal (no nested routes, no per-incident deep links); that belongs to F2.
* Hiding an entry is not a security control by itself; it is a courtesy backed by API refusals (tested for every offered entry and for entries not offered).
