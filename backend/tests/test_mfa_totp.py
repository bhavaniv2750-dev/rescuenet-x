"""S4: TOTP (RFC 6238), drift window, replay prevention, secret generation, and encryption of secrets at rest."""

import base64
import hashlib
import hmac
import struct
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pyotp
import pytest

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import MfaCredential
from app.services import mfa as mfa_svc
from app.services import mfa_crypto
from tests.conftest import enroll_mfa_directly, make_user, mfa_secret_of

BACKEND = Path(__file__).resolve().parent.parent

# RFC 6238 Appendix B (8-digit codes): the reference secrets are the ASCII strings repeated to each hash's block size
RFC_VECTORS = {
    "SHA1": (b"12345678901234567890", hashlib.sha1, {59: "94287082", 1111111109: "07081804", 1111111111: "14050471",
                                                  1234567890: "89005924", 2000000000: "69279037", 20000000000: "65353130"}),
    "SHA256": (b"12345678901234567890123456789012", hashlib.sha256, {59: "46119246", 1111111109: "68084774", 1111111111: "67062674",
                                                                  1234567890: "91819424", 2000000000: "90698825", 20000000000: "77737706"}),
    "SHA512": (b"1234567890123456789012345678901234567890123456789012345678901234", hashlib.sha512,
               {59: "90693936", 1111111109: "25091201", 1111111111: "99943326", 1234567890: "93441116", 2000000000: "38618901",
                20000000000: "47863826"}),
}


def rfc4226_independent(key: bytes, counter: int, digest, digits=8) -> str:
    """A from-scratch HOTP (RFC 4226) used only to cross-check the library against the RFC's own numbers."""
    mac = hmac.new(key, struct.pack(">Q", counter), digest).digest()
    off = mac[-1] & 0x0F
    return str((struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)).zfill(digits)


@pytest.mark.parametrize("algo", list(RFC_VECTORS))
def test_rfc_6238_test_vectors(algo):
    key, digest, vectors = RFC_VECTORS[algo]
    secret = base64.b32encode(key).decode()
    for t, expected in vectors.items():
        assert pyotp.TOTP(secret, digits=8, digest=digest).at(t) == expected                 # the library we use
        assert rfc4226_independent(key, t // 30, digest) == expected                          # an independent implementation


def test_our_six_digit_code_is_the_rfc_value_truncated_to_six_digits():
    secret = base64.b32encode(RFC_VECTORS["SHA1"][0]).decode()
    assert mfa_svc.code_for_step(secret, 59 // 30) == "287082"            # 94287082 -> last six digits
    assert mfa_svc.code_for_step(secret, 1111111109 // 30) == "081804"
    assert mfa_svc.STEP_SECONDS == 30 and mfa_svc.DIGITS == 6


@pytest.fixture
def clock(monkeypatch):
    state = {"t": 1_700_000_000.0}
    monkeypatch.setattr(mfa_svc, "_time", lambda: state["t"])
    return state


def test_drift_window_is_one_step_either_side_and_no_more(clock):
    secret = mfa_svc.new_secret()
    cur = mfa_svc.current_step()
    for offset, accepted in [(-2, False), (-1, True), (0, True), (1, True), (2, False), (-10, False)]:
        assert (mfa_svc.match_step(secret, mfa_svc.code_for_step(secret, cur + offset)) is not None) is accepted, offset
    assert mfa_svc.match_step(secret, mfa_svc.code_for_step(secret, cur + 1)) == cur + 1


def test_drift_setting_can_never_widen_beyond_one_step(clock, monkeypatch):
    monkeypatch.setattr(settings, "MFA_DRIFT_STEPS", 50)
    secret = mfa_svc.new_secret()
    cur = mfa_svc.current_step()
    assert mfa_svc.match_step(secret, mfa_svc.code_for_step(secret, cur + 3)) is None


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "12 34 5", "000000 ", None, "１２３４５６"])
def test_malformed_codes_never_match(bad):
    secret = mfa_svc.new_secret()
    assert mfa_svc.match_step(secret, bad or "") is None


def test_codes_for_a_different_secret_never_match():
    a, b = mfa_svc.new_secret(), mfa_svc.new_secret()
    assert mfa_svc.match_step(a, mfa_svc.code_for_step(b, mfa_svc.current_step())) is None


def test_replay_of_an_accepted_step_is_refused_and_a_later_step_is_accepted(clock):
    from app.db.session import SessionLocal
    uid, _ = make_user("CITIZEN")
    secret = enroll_mfa_directly(uid)
    db = SessionLocal()
    from app.models.entities import User
    user = db.get(User, uid)
    cur = mfa_svc.current_step()
    code = mfa_svc.code_for_step(secret, cur)
    assert mfa_svc.verify_totp(db, user, code) is True; db.commit()
    assert mfa_svc.verify_totp(db, user, code) is False                       # same code again: replay
    assert mfa_svc.verify_totp(db, user, mfa_svc.code_for_step(secret, cur - 1)) is False      # older step than accepted: refused
    clock["t"] += 30
    assert mfa_svc.verify_totp(db, user, mfa_svc.code_for_step(secret, cur + 1)) is True; db.commit()
    db.close()


def test_concurrent_use_of_one_code_has_exactly_one_winner():
    import threading
    uid, _ = make_user("CITIZEN")
    secret = enroll_mfa_directly(uid)
    from app.models.entities import User
    code = mfa_svc.code_for_step(secret, mfa_svc.current_step())
    results = []

    def go():
        db = SessionLocal()
        try:
            ok = mfa_svc.verify_totp(db, db.get(User, uid), code)
            db.commit()
            results.append(ok)
        finally:
            db.close()
    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count(True) == 1


# ---------------------------------------------------------------- secret generation and provisioning

def test_secrets_are_160_bit_random_base32_and_unique():
    secrets_ = {mfa_svc.new_secret() for _ in range(500)}
    assert len(secrets_) == 500
    assert all(len(s) == 32 and set(s) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for s in secrets_)      # 32 x 5 bits = 160 bits


def test_provisioning_uri_is_authenticator_compatible():
    secret = mfa_svc.new_secret()
    uri = mfa_svc.provisioning_uri(secret, "asha.rao")
    parsed = urllib.parse.urlparse(uri)
    q = dict(urllib.parse.parse_qsl(parsed.query))
    assert parsed.scheme == "otpauth" and parsed.netloc == "totp"
    assert urllib.parse.unquote(parsed.path) == "/RescueNet X:asha.rao"
    assert q["secret"] == secret and q["issuer"] == "RescueNet X"
    assert q.get("period", "30") == "30" and q.get("digits", "6") == "6" and q.get("algorithm", "SHA1") == "SHA1"


def test_qr_is_an_svg_data_uri_that_encodes_the_uri():
    uri = mfa_svc.provisioning_uri(mfa_svc.new_secret(), "x")
    qr = mfa_svc.qr_data_uri(uri)
    assert qr.startswith("data:image/svg+xml") and len(qr) > 500


# ---------------------------------------------------------------- encryption at rest

def test_encrypt_decrypt_round_trip_with_fresh_nonce_each_time():
    a, b = mfa_crypto.encrypt("JBSWY3DPEHPK3PXP", 7), mfa_crypto.encrypt("JBSWY3DPEHPK3PXP", 7)
    assert a != b and a.startswith("v1:") and "JBSWY3DPEHPK3PXP" not in a
    assert mfa_crypto.decrypt(a, 7) == mfa_crypto.decrypt(b, 7) == "JBSWY3DPEHPK3PXP"


def test_ciphertext_is_bound_to_the_user_and_tamper_evident():
    token = mfa_crypto.encrypt("SECRETSECRETSECRET", 5)
    with pytest.raises(mfa_crypto.MfaDecryptError):
        mfa_crypto.decrypt(token, 6)                                       # copied to another account
    v, kid, blob = token.split(":")
    flipped = blob[:-2] + ("AA" if not blob.endswith("AA") else "BB")
    with pytest.raises(mfa_crypto.MfaDecryptError):
        mfa_crypto.decrypt(f"{v}:{kid}:{flipped}", 5)                      # modified ciphertext
    with pytest.raises(mfa_crypto.MfaDecryptError):
        mfa_crypto.decrypt("v1:nokey:" + blob, 5)                          # unknown key id
    with pytest.raises(mfa_crypto.MfaDecryptError):
        mfa_crypto.decrypt("garbage", 5)


def test_key_rotation_old_ciphertext_still_decrypts_and_new_writes_use_the_new_key(monkeypatch):
    old_spec = settings.MFA_ENCRYPTION_KEYS
    old_token = mfa_crypto.encrypt("ROTATEMEROTATEME", 9)
    new = mfa_crypto.new_key()
    monkeypatch.setattr(settings, "MFA_ENCRYPTION_KEYS", f"fresh:{new},{old_spec}")
    assert mfa_crypto.primary_key_id() == "fresh"
    assert mfa_crypto.decrypt(old_token, 9) == "ROTATEMEROTATEME"
    assert mfa_crypto.key_id_of(mfa_crypto.encrypt("X" * 16, 9)) == "fresh"
    monkeypatch.setattr(settings, "MFA_ENCRYPTION_KEYS", f"fresh:{new}")          # old key removed too early
    with pytest.raises(mfa_crypto.MfaDecryptError):
        mfa_crypto.decrypt(old_token, 9)


@pytest.mark.parametrize("spec", ["short:abc", "k:" + "A" * 60, "k:!!!notbase64!!!", "a:" + "A" * 43 + ",a:" + "B" * 43, "bad id:" + "A" * 43])
def test_invalid_key_configurations_are_rejected(spec, monkeypatch):
    monkeypatch.setattr(settings, "MFA_ENCRYPTION_KEYS", spec)
    with pytest.raises(mfa_crypto.MfaKeyError):
        mfa_crypto.load_keys()


def test_development_without_a_key_creates_a_local_key_file_but_production_never_does(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MFA_ENCRYPTION_KEYS", "")
    monkeypatch.setattr(mfa_crypto, "DEV_KEY_FILE", tmp_path / ".mfa_key")
    assert settings.is_development
    token = mfa_crypto.encrypt("DEVONLYSECRETXXXX", 1)
    assert (tmp_path / ".mfa_key").exists() and oct((tmp_path / ".mfa_key").stat().st_mode & 0o777) == "0o600"
    assert mfa_crypto.decrypt(token, 1) == "DEVONLYSECRETXXXX"
    monkeypatch.setattr(settings, "RESCUENET_ENV", "production")
    (tmp_path / ".mfa_key").unlink()
    with pytest.raises(mfa_crypto.MfaKeyError):
        mfa_crypto.load_keys()
    assert not (tmp_path / ".mfa_key").exists()                           # production did not fall back to a generated key


def test_stored_secret_is_ciphertext_and_the_plaintext_is_in_no_table():
    import sqlite3
    uid, _ = make_user("CITIZEN")
    secret = enroll_mfa_directly(uid)
    db = SessionLocal()
    row = db.query(MfaCredential).filter(MfaCredential.user_id == uid).one()
    assert secret not in row.secret_enc and row.secret_enc.startswith("v1:")
    path = str(db.get_bind().url).replace("sqlite:///", ""); db.close()
    raw = sqlite3.connect(path)
    for (table,) in raw.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for r in raw.execute(f'SELECT * FROM "{table}"'):
            assert secret not in " ".join(str(v) for v in r), table
    raw.close()


def test_encryption_key_is_not_in_the_database_or_the_repository_files():
    key_material = settings.MFA_ENCRYPTION_KEYS.split(":", 1)[1].split(",")[0]
    import sqlite3
    db = SessionLocal(); path = str(db.get_bind().url).replace("sqlite:///", ""); db.close()
    assert key_material.encode() not in Path(path).read_bytes()
    tracked = subprocess.run(["git", "ls-files"], cwd=BACKEND.parent, capture_output=True, text=True).stdout.splitlines()
    for f in tracked:
        p = BACKEND.parent / f
        if p.suffix in (".py", ".md", ".json", ".env", ".example", ".txt", ".ts", ".tsx") and p.is_file() and p.stat().st_size < 2_000_000:
            assert key_material not in p.read_text(errors="ignore"), f"test key material found in {f}"
