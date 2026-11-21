"""Flood photo analysis endpoints (pretrained CLIP + SegFormer, see services/vision_service.py)."""

import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.vision_service import VisionModelUnavailable, flood_vision_service

router = APIRouter()

MAX_BYTES = 10 * 1024 * 1024
EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@router.get("/status")
def vision_status():
    return flood_vision_service.status()


async def _analyze(data: bytes, overlay: bool):
    try:
        return await run_in_threadpool(flood_vision_service.analyze, data, overlay)
    except VisionModelUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except OSError as e:  # not a readable image
        raise HTTPException(status_code=422, detail=f"Could not read image: {e}")


@router.post("/analyze")
async def analyze_upload(file: UploadFile = File(...), overlay: bool = Query(True)):
    if Path(file.filename or "").suffix.lower() not in EXTS:
        raise HTTPException(status_code=400, detail=f"Allowed formats: {', '.join(sorted(EXTS))}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds maximum 10MB limit")
    return await _analyze(data, overlay)


@router.get("/dataset/{filename}")
async def analyze_dataset_image(filename: str, overlay: bool = Query(True)):
    safe = os.path.basename(filename)
    if not safe or safe != filename:
        raise HTTPException(status_code=400, detail="Invalid filename format")
    path = (settings.FLOOD_IMG_DIR / safe).resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Image {safe} not found")
    result = await _analyze(path.read_bytes(), overlay)
    result["filename"] = safe
    return result
