"""Development-only helpers. Every route answers 404 unless RESCUENET_ENV=development AND the caller is on this machine."""

from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.services import notifications as notif
from app.services.rate_limit import client_ip

router = APIRouter()
LOCAL = {"127.0.0.1", "::1", "localhost", "testclient", "local"}


def _only_local_development(request: Request) -> None:
    if not settings.is_development or client_ip(request) not in LOCAL:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/outbox")
def development_outbox(request: Request):
    """Messages the development outbox holds (verification codes, reset links). NOTHING in it was delivered to anyone."""
    _only_local_development(request)
    return {"notice": notif.DEV_NOTICE, "items": notif.dev_outbox()}
