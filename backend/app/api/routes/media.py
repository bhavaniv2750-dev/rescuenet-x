"""Authorised access to evidence photographs. This is the only route that serves them."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user
from app.db.session import get_db
from app.models.entities import MediaAsset, User
from app.services import media

router = APIRouter()


@router.get("/{asset_id}")
def get_media(asset_id: str, db: Session = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    if user is None:  # same answer whether or not the id exists
        raise HTTPException(status_code=401, detail="Sign in required", headers={"WWW-Authenticate": "Bearer"})
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first() if len(asset_id) == 32 else None
    path = media.asset_path(asset) if asset else None
    if asset is None or not media.can_view(db, asset, user) or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")  # never reveals that a private photo exists
    return FileResponse(path, media_type=asset.content_type, headers=media.PRIVATE_HEADERS)
