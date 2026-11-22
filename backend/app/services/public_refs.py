"""Public report references and tracking codes.

* public_ref     identifies a report to its reporter, e.g. RN-7K2F-9QXM-4TBD. 60 random bits. Not a secret and not
                 derived from the internal incident id or from a counter, so it cannot be guessed from other ids.
* tracking_code  the secret that unlocks the limited status view. 100 random bits (Crockford base32), shown once.
                 Only its SHA-256 is stored, and it is compared in constant time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U


def _random(n: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def _group(s: str, size: int = 4) -> str:
    return "-".join(s[i:i + size] for i in range(0, len(s), size))


def new_public_ref() -> str:
    return "RN-" + _group(_random(12))


def new_tracking_code() -> str:
    return _group(_random(20))


def normalise(value: str) -> str:
    """Accept lower case, spaces and the look-alike letters people mistype (O->0, I/L->1)."""
    v = "".join(ch for ch in value.upper() if ch.isalnum())
    return v.replace("O", "0").replace("I", "1").replace("L", "1")


def hash_code(code: str) -> str:
    return hashlib.sha256(normalise(code).encode()).hexdigest()


_DUMMY = hash_code("0" * 20)


def code_matches(code: str, stored_hash: str | None) -> bool:
    """Constant-time comparison; does the same work when the report does not exist."""
    candidate = hash_code(code or "")
    return hmac.compare_digest(candidate, stored_hash or _DUMMY) and stored_hash is not None


def normalise_ref(ref: str) -> str:
    body = normalise(ref)
    if body.startswith("RN"):
        body = body[2:]
    return "RN-" + _group(body) if len(body) == 12 else ""
