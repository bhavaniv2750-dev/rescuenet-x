# M0 evidence: backup/restore, Alembic baseline, environment flag

No application behaviour changed. All runs used throwaway or copied databases; the operator's own database was not modified.

## Tests
| Suite | Result |
|---|---|
| Full backend suite | 151 passed, 1 skipped (live Ollama), was 134 + 1 before M0 |
| P0 dispatch-safety (`test_p0_safety.py`, `test_team_selection.py`, files unchanged) | 66 passed |
| New: `test_migrations.py` (10), `test_backup_restore.py` (7) | 17 passed |
| Frontend `npm run build` | succeeded |
| `pip-audit -r backend/requirements.txt` | no known vulnerabilities |

## Migration and rollback evidence (copy of a real older database, 8 tables, pre-auth schema)
1. Manual backup: integrity `ok`, SHA-256 recorded, manifest holds table names and row counts only.
2. First start: automatic verified `pre-baseline` backup; 23 missing columns, 3 missing tables, 4 missing indexes added; stamped `0001`.
   All existing rows preserved. Only `incidents.status` changed (legacy `ASSIGNED`/`IN_PROGRESS` renamed); the backup retains the old values.
3. Second start: no-op, no extra backup.
4. Restore of the `pre-baseline` backup: dry run changed nothing; real restore reproduced the original data exactly
   (logical hash of every original column identical); previous state kept as a `pre-restore` backup.
   Raw file bytes differ from the original because SQLite's backup API rewrites pages; contents are identical.
5. Up/down/up on an empty database: identical schema; no drift between migrations and models (a test fails if a model changes without a migration).
6. If the backup cannot be written, the database is not changed and start-up is refused (tested).

## Defect found and fixed during validation
`ensure_schema()` silently depended on another module having imported the models; run standalone against the real older
database it failed. It now imports them itself; regression test `test_ensure_schema_works_when_nothing_else_imported_the_models`
fails without the fix.

## Remaining risks
- Columns added to older SQLite tables stay nullable (cannot be changed without a table rebuild); documented.
- Backups are local files with owner-only permissions; they must be copied off the machine to be a real safety net.
- `RESCUENET_ENV` defaults to `production`; nothing keys off it yet (used from S5).
