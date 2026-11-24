"""Encryption of TOTP secrets at rest (AES-256-GCM, authenticated) and its key management.

* Keys come from the environment (MFA_ENCRYPTION_KEYS="kid:KEY[,kid2:KEY2]", first = primary), never from the database. A key is
  32 random bytes, base64url-encoded: `python scripts/mfa_keys.py generate`.
* Stored value: "v1:<kid>:<base64url(nonce || ciphertext+tag)>". The user id is bound as associated data, so a ciphertext copied
  to another account fails authentication.
* Rotation: add the new key FIRST in the list, run `python scripts/mfa_keys.py rotate`, then remove the old key.
* Production refuses to start without a valid key (validate_configuration). Development, with no key set, creates
  backend/.mfa_key once (git-ignored, mode 0600): a convenience that never applies in production.
* Losing every key makes all stored secrets unreadable; affected users must be reset with the host-level tool and re-enrol
  (docs/security/S4_MFA.md).
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets
from pathlib import Path
from typing import Dict, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import BASE_DIR, settings

KEY_BYTES = 32
DEV_KEY_FILE = Path(BASE_DIR) / "backend" / ".mfa_key"


class MfaKeyError(RuntimeError):
    """Missing or invalid MFA encryption configuration."""


class MfaDecryptError(RuntimeError):
    """A stored secret could not be decrypted (wrong/lost key, or tampered)."""


def new_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(KEY_BYTES)).decode().rstrip("=")


def _decode_key(text: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as exc:
        raise MfaKeyError("MFA encryption key is not valid base64url") from exc
    if len(raw) != KEY_BYTES:
        raise MfaKeyError(f"MFA encryption key must be exactly {KEY_BYTES} bytes ({KEY_BYTES * 8}-bit) after decoding")
    return raw


def parse_keys(spec: str) -> Dict[str, bytes]:
    """Ordered {kid: key}. The first entry is the primary (encrypting) key."""
    keys: Dict[str, bytes] = {}
    for i, part in enumerate(p.strip() for p in spec.split(",") if p.strip()):
        kid, sep, key = part.partition(":")
        if not sep:                      # a bare key (the single-key form)
            kid, key = f"k{i + 1}", part
        if not kid.replace("-", "").replace("_", "").isalnum() or kid in keys:
            raise MfaKeyError("MFA key ids must be alphanumeric and unique")
        keys[kid] = _decode_key(key.strip())
    return keys


def _dev_key_spec() -> str:
    if DEV_KEY_FILE.exists():
        return DEV_KEY_FILE.read_text().strip()
    spec = "dev:" + new_key()
    try:
        DEV_KEY_FILE.write_text(spec + "\n")
        os.chmod(DEV_KEY_FILE, 0o600)
    except OSError:
        pass
    return spec


def load_keys() -> Dict[str, bytes]:
    spec = settings.MFA_ENCRYPTION_KEYS.strip()
    if not spec:
        if settings.is_production:
            raise MfaKeyError("MFA_ENCRYPTION_KEYS is not set. Production requires an encryption key for TOTP secrets "
                              "(generate one with: python scripts/mfa_keys.py generate).")
        spec = _dev_key_spec()          # development only
    keys = parse_keys(spec)
    if not keys:
        raise MfaKeyError("MFA_ENCRYPTION_KEYS contains no key")
    return keys


def validate_configuration() -> None:
    """Called at start-up. Raises MfaKeyError (the app refuses to run) for a missing or invalid configuration in production,
    and for an invalid one anywhere."""
    load_keys()


def primary_key_id() -> str:
    return next(iter(load_keys()))


def encrypt(plaintext: str, user_id: int) -> str:
    keys = load_keys()
    kid, key = next(iter(keys.items()))
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), f"mfa:{user_id}".encode())
    return f"v1:{kid}:{base64.urlsafe_b64encode(nonce + ct).decode().rstrip('=')}"


def key_id_of(token: str) -> Optional[str]:
    parts = (token or "").split(":")
    return parts[1] if len(parts) == 3 and parts[0] == "v1" else None


def decrypt(token: str, user_id: int) -> str:
    try:
        version, kid, blob = token.split(":")
        if version != "v1":
            raise ValueError
        raw = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
        key = load_keys().get(kid)
        if key is None:
            raise MfaDecryptError(f"the key '{kid}' that encrypted this secret is not configured")
        return AESGCM(key).decrypt(raw[:12], raw[12:], f"mfa:{user_id}".encode()).decode()
    except MfaDecryptError:
        raise
    except (InvalidTag, ValueError, binascii.Error) as exc:
        raise MfaDecryptError("stored MFA secret failed authentication") from exc
