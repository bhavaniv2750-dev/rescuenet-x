# S0 evidence: private evidence photos, safe guest uploads, random public references

## What was wrong (verified at ee70be3)
- `GET /api/incidents/uploads/{file}` served any uploaded photo to anyone (probe: FAIL before, `probe_exposure_BEFORE_fix_output.txt`).
- Guest uploads: no rate limit or quota, type judged by file extension, files stored as received (EXIF/GPS and any appended payload kept).
- Incident ids were a counter (`INC-1045 + count`): predictable, leaked report volume, could repeat after a delete.
- There was no way for a guest to follow a report.

## What changed
| Area | Change |
|---|---|
| Photos | Only served by `GET /api/media/{id}` after an access check: staff (admin/commander/operator), the responder whose team is assigned, the report's own signed-in owner. Everyone else 404; anonymous 401 (same answer whether or not the id exists). `Cache-Control: private, no-store`, `nosniff`. No static mount. Old route now needs sign-in + the same permission. |
| Uploads | Decoded with Pillow (name and Content-Type ignored); JPEG/PNG/WebP only; 5 MB cap checked while reading; 25 MP decoded cap; animated images refused; downscaled to 2048 px; re-encoded from pixels as a fresh JPEG (EXIF/GPS, comments, ICC, appended payloads gone); random 128-bit names. |
| Limits | 5 photos per report; guest uploads 25/hour per connection, 50 MB/day, 10 waiting at once; storage quota 2 GB; guest reports 10/hour per connection; signed-in users 60/hour. Abandoned uploads purged after 24 h; attached evidence never purged. |
| Never blocks reporting | A rejected, expired or over-quota photo is returned as a warning; the report is still saved. 429 messages tell people to call 112. |
| References | `public_ref` (60 random bits, not secret) + `tracking_code` (100 random bits, shown once, only SHA-256 stored, constant-time compare). New internal ids are random (`INC-XXXXXXXX`). |
| Tracking | `GET /api/public/reports/{ref}` with `X-Tracking-Code` header; returns only status, timestamps, photo count. Unknown reference, wrong code and missing code give identical 404s. 10 failures / 15 min and 60 lookups / hour per connection, then 429 (even the right code is refused during lock-out). |
| Proxy | `X-Forwarded-For` is ignored unless `TRUSTED_PROXY_COUNT` is set (forged headers cannot bypass limits; tested). |
| Frontend | Staff views load photos with the sign-in token; guests get a receipt (reference + one-time code) that stays on screen across pages; "Track a report" on the home page; browser-side resize so ordinary phone photos fit 5 MB. |
| Migration | `0002`: new table/columns, random refs for existing incidents. `scripts/migrate_legacy_media.py` (dry run by default) moves old photos under the new rules, never deleting originals. |

## Tests
- Backend: 206 passed, 1 skipped (live Ollama). New: `test_public_media.py` (33), `test_public_refs.py` (20), migration tests (+2).
- P0 dispatch-safety suites (66 tests): unchanged files, all pass.
- `npm run build`: passes. (`npm run lint` already reported many `any` errors before this work; not touched.)
- Black-box probe, before vs after: `probe_exposure_BEFORE_fix_output.txt` (EXPOSURE FOUND) vs `probe_exposure_output.txt` (no exposure found). The before-run's "report" failure is only because `/api/public/reports` did not exist yet.

## Browser evidence (390 px guest, 1366 px staff; synthetic 9.5 MB test photo, isolated temporary database)
01 guest home, 02 report with a 9.5 MB photo (resized in the browser, stored as ~1 MB JPEG), 03 receipt with reference and code,
04 wrong code (generic message), 05 correct code ("Received, 1 photo attached"), 07 staff view where the photo loads (HTTP 200 with token).

## Findings and remaining risks
- The repo's local `backend/rescuenet.db` was never tracked by git (verified across all history), so no untracking was needed; WAL/shm/backup patterns were added to `.gitignore` in M0.
- Three test images were committed in early history (`backend/uploads/*`, removed later): a 512x384 JPEG with no EXIF/GPS, a 1x1 test pixel and a documentation diagram. No real private photographs or credentials were found. The default demo password in `config.py` is public in the source and history; it is for development only and must never be used in a real deployment (production removal is milestone S5).
- Rate limits are per process and reset on restart; behind several workers use proxy-level limits too.
- Connection fingerprints are keyed hashes of the client address; shared networks (one address, many people) share limits.
- Guests cannot view their own photo again after submitting (they have the original). Signed-in owners can.
- Admin can still see all evidence until the S1 role separation.
- Pages still load Leaflet CSS and fonts from CDNs (browser run contacted fonts.googleapis.com, unpkg.com, fonts.gstatic.com); fixed in F0.
- Rotation: no credential in the audited database or uploads required rotation. The database held no user table (it predates sign-in), so no accounts or password hashes.
