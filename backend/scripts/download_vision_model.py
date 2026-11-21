"""Download the pretrained flood-photo models (about 105 MB) into backend/app/ml/artifacts/vision/.

The backend also downloads them on the first photo analysis; run this once while
online if the demo machine may be offline later.

Usage (from backend/): python scripts/download_vision_model.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.vision_service import CLIP_FILE, MODEL_DIR, MODEL_FILE, download_model  # noqa: E402

if __name__ == "__main__":
    download_model()
    for f in (MODEL_FILE, CLIP_FILE):
        print(f"{f.name}: {f.stat().st_size / 1e6:.1f} MB")
    print(f"Models ready in {MODEL_DIR}")
