# Backup, migration and rollback procedures

Applies to the SQLite database (`DATABASE_URL`, default `backend/rescuenet.db`). Run commands from `backend/`.

## Before any upgrade
```bash
python scripts/backup_db.py --label before-upgrade
```
Writes `backups/<db>-<UTC time>-<label>.db.bak` plus a `.manifest.json` (SHA-256, integrity result, table row counts;
never record contents). Backups are created with owner-only permissions and are git-ignored. Copy them off the machine:
they contain real records.

The application also takes a verified backup automatically before it migrates an existing database. If that backup
cannot be written, the database is **not** changed and the app refuses to start.

## Check a backup
```bash
python scripts/backup_db.py --verify backups/<file>.db.bak
```

## Roll back
1. **Stop the application.**
2. Preview, then restore (the database being replaced is saved first as a `pre-restore` backup):
```bash
python scripts/restore_db.py backups/<file>.db.bak          # dry run
python scripts/restore_db.py backups/<file>.db.bak --yes
```
3. Restore the matching application version (`git checkout <previous commit>`); an older build must not run against a
   newer schema.
4. Start the app and check `/api/health`.

Schema-only rollback (when no data was written under the new schema):
```bash
alembic downgrade <previous revision>
```
Every revision has a tested `downgrade()`. Restoring the backup is the safer path whenever data may have changed.

## What the first start on an older database does
Databases created before Alembic are backed up (`pre-baseline`), brought up to date with the legacy helper
(missing tables, columns, indexes; legacy incident statuses `ASSIGNED`/`IN_PROGRESS` renamed to
`DISPATCHED`/`ON_SCENE`), checked, then stamped as revision `0001`. Existing rows are never deleted. Known limitation:
columns added to an older SQLite table stay nullable (SQLite cannot change that without rebuilding the table).

## Limits
Backups are point-in-time files, not continuous. SQLite is single-node. Restoring replaces **all** data changed since
the backup. Do not restore while the app is running.
