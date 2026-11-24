"""MFA encryption key tools.

    python scripts/mfa_keys.py generate     # print a new key (put it in MFA_ENCRYPTION_KEYS; keep it out of the database/repo)
    python scripts/mfa_keys.py check        # can every stored TOTP secret be decrypted with the configured keys?
    python scripts/mfa_keys.py rotate       # re-encrypt every stored secret with the PRIMARY (first) configured key

Rotation: 1) generate a new key, 2) put it FIRST in MFA_ENCRYPTION_KEYS ("new:KEY2,old:KEY1"), 3) restart, 4) run `rotate`
(takes a verified backup first), 5) run `check`, 6) later remove the old key. Output never contains a secret or a key.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.db import backup as backup_mod  # noqa: E402
from app.db.migrations import ensure_schema  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.entities import MfaCredential  # noqa: E402
from app.services import mfa_crypto  # noqa: E402


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "generate":
        print(mfa_crypto.new_key())
        return 0
    if cmd not in ("check", "rotate"):
        print(__doc__)
        return 2
    mfa_crypto.validate_configuration()
    ensure_schema(engine)
    if cmd == "rotate" and engine.dialect.name == "sqlite":
        path = backup_mod.sqlite_path_from_url(str(engine.url))
        if path.is_file():
            bk = backup_mod.create_backup(path, settings.BACKUP_DIR, "pre-mfa-key-rotation")
            backup_mod.verify_backup(bk)
            print(f"Backup written and verified: {bk.name}")
    primary = mfa_crypto.primary_key_id()
    db = SessionLocal()
    bad, moved, total = [], 0, 0
    try:
        for cred in db.query(MfaCredential).all():
            total += 1
            try:
                clear = mfa_crypto.decrypt(cred.secret_enc, cred.user_id)
            except mfa_crypto.MfaDecryptError:
                bad.append(cred.user_id)
                continue
            if cmd == "rotate" and mfa_crypto.key_id_of(cred.secret_enc) != primary:
                cred.secret_enc = mfa_crypto.encrypt(clear, cred.user_id)
                moved += 1
        if cmd == "rotate":
            db.commit()
    finally:
        db.close()
    print(f"credentials: {total}; undecryptable: {len(bad)}" + (f" (user ids {bad})" if bad else "")
          + (f"; re-encrypted: {moved}" if cmd == "rotate" else ""))
    if bad:
        print("Undecryptable accounts need host-level recovery: scripts/account_admin.py reset-mfa (see docs/security/S4_MFA.md).")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
