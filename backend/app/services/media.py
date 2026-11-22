"""Evidence photographs: validation, safe re-encoding, storage and access rules.

Nothing the client sends is trusted: size is capped while reading, the type comes from decoding the bytes (never the
file name or Content-Type), decoded dimensions are bounded, and the stored file is a fresh JPEG built from pixel data
only, so EXIF/GPS, comments, embedded thumbnails, ICC profiles and any appended or polyglot payload are gone.
Stored names are random and carry no information from the upload. Files are only ever served through
GET /api/media/{asset_id} after an authorisation check (see can_view).
"""

from __future__ import annotations

import hashlib
import io
import secrets
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Incident, MediaAsset, User

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}   # animated GIFs and everything else are refused
MEDIA_URL_PREFIX = "/api/media/"
LEGACY_URL_PREFIX = "/api/incidents/uploads/"
from app.core.permissions import P, has_permission
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                   "Content-Disposition": 'inline; filename="evidence.jpg"'}


class MediaRejected(ValueError):
    """Raised with a message that is safe to show to the uploader."""


@dataclass
class Processed:
    data: bytes
    width: int
    height: int


def read_limited(stream, limit: int) -> bytes:
    """Read at most `limit` bytes; refuse larger bodies without buffering them."""
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise MediaRejected(f"Image is larger than {limit // (1024 * 1024)} MB.")
    if not data:
        raise MediaRejected("The uploaded file is empty.")
    return data


def process_image(raw: bytes, max_bytes: int | None = None) -> Processed:
    """Decode, bound, strip and re-encode. Raises MediaRejected for anything that is not a plain photo."""
    limit = max_bytes or settings.MAX_IMAGE_BYTES
    if len(raw) > limit:
        raise MediaRejected(f"Image is larger than {limit // (1024 * 1024)} MB.")
    Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(io.BytesIO(raw))
            fmt = probe.format
            if fmt not in ALLOWED_FORMATS:
                raise MediaRejected("Only JPEG, PNG or WebP photos are accepted.")
            if getattr(probe, "is_animated", False) or getattr(probe, "n_frames", 1) > 1:
                raise MediaRejected("Animated images are not accepted.")
            w, h = probe.size
            if w < 1 or h < 1 or w * h > settings.MAX_IMAGE_PIXELS:
                raise MediaRejected("Image dimensions are too large.")
            probe.verify()                      # structural check; the file object is unusable afterwards
            img = Image.open(io.BytesIO(raw))   # reopen for a full decode
            img.load()
    except MediaRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError,
            SyntaxError, ValueError, MemoryError, EOFError):
        raise MediaRejected("The file could not be read as a valid photo.") from None

    img = ImageOps.exif_transpose(img)          # honour orientation before the metadata is dropped
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((settings.IMAGE_MAX_SIDE_PX, settings.IMAGE_MAX_SIDE_PX))

    clean = Image.new("RGB", img.size)          # a new image holds pixels only: no info dict, no EXIF
    clean.paste(img)
    out = io.BytesIO()
    clean.save(out, format="JPEG", quality=85, optimize=True)
    return Processed(out.getvalue(), clean.width, clean.height)


def asset_path(asset: MediaAsset) -> Path:
    return settings.UPLOAD_DIR / asset.stored_name


def storage_used_bytes(db: Session) -> int:
    return int(db.query(func.coalesce(func.sum(MediaAsset.size_bytes), 0)).scalar() or 0)


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def purge_abandoned(db: Session) -> int:
    """Delete uploads that were never attached to a report and are past their window. Attached evidence is never touched."""
    cutoff = now_utc() - timedelta(hours=24)
    stale = db.query(MediaAsset).filter(MediaAsset.incident_id.is_(None), MediaAsset.created_at < cutoff).all()
    for a in stale:
        asset_path(a).unlink(missing_ok=True)
        db.delete(a)
    if stale:
        db.commit()
    return len(stale)


def store_upload(db: Session, raw: bytes, *, user: Optional[User], client_hash: str) -> MediaAsset:
    """Validate, enforce quotas, write the re-encoded file and register it (unattached)."""
    purge_abandoned(db)
    day_ago = now_utc() - timedelta(hours=24)

    if storage_used_bytes(db) + len(raw) > settings.UPLOAD_QUOTA_MB * 1024 * 1024:
        raise MediaRejected("Photo storage is full right now. You can still send your report without a photo.")
    waiting = db.query(MediaAsset).filter(MediaAsset.uploader_hash == client_hash, MediaAsset.incident_id.is_(None),
                                          MediaAsset.created_at > now_utc() - timedelta(minutes=settings.UNATTACHED_UPLOAD_TTL_MINUTES)).count()
    if waiting >= settings.MAX_UNATTACHED_UPLOADS_PER_CLIENT:
        raise MediaRejected("Too many photos are waiting to be attached to a report. Send the report first.")
    if user is None:
        used = db.query(func.coalesce(func.sum(MediaAsset.size_bytes), 0)).filter(
            MediaAsset.uploader_hash == client_hash, MediaAsset.uploader_user_id.is_(None), MediaAsset.created_at > day_ago).scalar() or 0
        if used + len(raw) > settings.GUEST_UPLOAD_MB_PER_DAY * 1024 * 1024:
            raise MediaRejected("Daily photo upload limit reached for this connection. You can still send your report without a photo.")

    processed = process_image(raw)
    asset_id = secrets.token_hex(16)                 # 128-bit capability; also the stored file name
    stored_name = f"{asset_id}.jpg"
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = settings.UPLOAD_DIR / stored_name
    with open(path, "xb") as fh:                      # "x": never overwrite
        fh.write(processed.data)
    asset = MediaAsset(
        id=asset_id, stored_name=stored_name, content_type="image/jpeg", size_bytes=len(processed.data),
        width=processed.width, height=processed.height, sha256=hashlib.sha256(processed.data).hexdigest(),
        uploader_user_id=user.id if user else None, uploader_hash=client_hash, privacy="PRIVATE", created_at=now_utc())
    db.add(asset)
    db.commit()
    return asset


def asset_id_from_url(url: Optional[str]) -> Optional[str]:
    if url and url.startswith(MEDIA_URL_PREFIX):
        rest = url[len(MEDIA_URL_PREFIX):]
        if len(rest) == 32 and all(c in "0123456789abcdef" for c in rest):
            return rest
    return None


def attach_to_incident(db: Session, image_urls: list[str], incident: Incident, user: Optional[User]) -> list[MediaAsset]:
    """Attach freshly uploaded, still-unattached photos to a new report. Anything else is refused."""
    if len(image_urls) > settings.MAX_IMAGES_PER_REPORT:
        raise MediaRejected(f"At most {settings.MAX_IMAGES_PER_REPORT} photos can be attached to one report.")
    attached = []
    cutoff = now_utc() - timedelta(minutes=settings.UNATTACHED_UPLOAD_TTL_MINUTES)
    for url in dict.fromkeys(image_urls):          # de-duplicate, keep order
        aid = asset_id_from_url(url)
        asset = db.query(MediaAsset).filter(MediaAsset.id == aid).first() if aid else None
        ok = (asset is not None and asset.incident_id is None and asset.created_at >= cutoff
              and (asset.uploader_user_id is None or (user is not None and asset.uploader_user_id == user.id)))
        if not ok:
            raise MediaRejected("A photo could not be attached: it was not uploaded recently or is already in use. Upload it again.")
        asset.incident_id = incident.id
        attached.append(asset)
    return attached


def can_view_incident_evidence(inc: Incident, user: Optional[User]) -> bool:
    """Who may see the evidence photos of an incident (permission-based, see app.core.permissions).

    * evidence.view_all (commander, operator): every incident
    * evidence.view_assigned (rescue officer): only incidents assigned to the officer's own team
    * evidence.view_own (citizen, volunteer): only their own reports
    * administrators and developers hold none of these
    * anonymous callers: never
    """
    if user is None:
        return False
    if has_permission(user, P.EVIDENCE_VIEW_ALL):
        return True
    if has_permission(user, P.EVIDENCE_VIEW_ASSIGNED) and user.team_id and inc.assigned_team_id == user.team_id:
        return True
    return has_permission(user, P.EVIDENCE_VIEW_OWN) and inc.reporter_user_id == user.id


def can_view(db: Session, asset: MediaAsset, user: Optional[User]) -> bool:
    """Who may see one evidence photo: the rules above, or the signed-in uploader before it is attached."""
    if user is None:
        return False
    if asset.incident_id is None:
        return asset.uploader_user_id == user.id
    inc = db.query(Incident).filter(Incident.id == asset.incident_id).first()
    return inc is not None and can_view_incident_evidence(inc, user)


def asset_for_legacy_filename(db: Session, filename: str) -> Optional[Incident]:
    return db.query(Incident).filter(Incident.image_url == f"{LEGACY_URL_PREFIX}{filename}").first()


def import_legacy_uploads(db: Session, apply: bool = False) -> dict:
    """Bring photos stored by the old public route (/api/incidents/uploads/<file>) under the new rules.

    Each photo is decoded and re-encoded without metadata into a private media asset attached to its incident, and the
    incident's image_url is switched to /api/media/<id>. Original files are NEVER deleted or modified; the old URL is
    kept in media_assets.legacy_source so the change can be reversed. Without apply=True nothing is written.
    Returns counts and incident ids only.
    """
    report = {"found": 0, "importable": 0, "imported": 0, "missing_file": [], "rejected": []}
    legacy_cap = 10 * 1024 * 1024  # the old limit
    for inc in db.query(Incident).filter(Incident.image_url.like(f"{LEGACY_URL_PREFIX}%")).all():
        report["found"] += 1
        name = Path(inc.image_url[len(LEGACY_URL_PREFIX):]).name
        src = settings.UPLOAD_DIR / name
        if not src.is_file():
            report["missing_file"].append(inc.id)
            continue
        try:
            processed = process_image(src.read_bytes(), max_bytes=legacy_cap)
        except MediaRejected:
            report["rejected"].append(inc.id)
            continue
        report["importable"] += 1
        if not apply:
            continue
        asset_id = secrets.token_hex(16)
        with open(settings.UPLOAD_DIR / f"{asset_id}.jpg", "xb") as fh:
            fh.write(processed.data)
        db.add(MediaAsset(id=asset_id, incident_id=inc.id, stored_name=f"{asset_id}.jpg", content_type="image/jpeg",
                          size_bytes=len(processed.data), width=processed.width, height=processed.height,
                          sha256=hashlib.sha256(processed.data).hexdigest(), privacy="PRIVATE",
                          legacy_source=inc.image_url, created_at=now_utc()))
        inc.image_url = f"{MEDIA_URL_PREFIX}{asset_id}"
        report["imported"] += 1
    if apply:
        db.commit()
    return report
