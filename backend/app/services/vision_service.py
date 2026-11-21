"""Flood photo analysis with two pretrained models, run through ONNX Runtime on the CPU.

1. CLIP ViT-B/32 (zero-shot scene classifier) decides whether the photo shows a
   flood, by comparing the photo with fixed text prompts ("a photo of a flooded
   street", "a photo of the sea", ...). Prompt vectors are precomputed by
   scripts/build_clip_prompts.py.
2. SegFormer-B0 fine-tuned on ADE20K (150 scene classes, including water, sea,
   river, lake, person, car, bus, truck and boat) labels every pixel, which gives
   the water coverage and which people and vehicles are standing in water.
No training on our photos is involved: both models are used as published.

The service reports:
  * flood detected: CLIP flood probability of at least 0.5;
  * water coverage: share of the image SegFormer labels water, sea, river or lake;
  * people, vehicles and boats, and which of them touch water;
  * a suggested severity built from those facts.

Results are labelled PREDICTED and support, not replace, a responder's judgement.

Water depth is not estimated. Two single-photo methods were tried (object
height-to-width ratio, and whether an object's outline is cut flat by the
waterline); neither separated shallow from deep water on our photos, because
camera angle and reflections dominate at this resolution. The reporter enters
the depth instead.
Known weakness: SegFormer sometimes labels brown, muddy floodwater as earth or
floor, so the water coverage can be low on a photo that CLIP still calls a flood.
See docs/vision_evaluation.md for measured detection and false-alarm rates.
"""

from __future__ import annotations

import base64
import io
import json
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from app.core.config import settings

CLIP_REPO = "Xenova/clip-vit-base-patch32"
HF_REPO = "Xenova/segformer-b0-finetuned-ade-512-512"
MODEL_DIR = settings.MODELS_DIR / "vision"
MODEL_FILE = MODEL_DIR / "segformer_b0_ade20k.onnx"
LABELS_FILE = MODEL_DIR / "segformer_b0_ade20k_labels.json"
MODEL_URL = f"https://huggingface.co/{HF_REPO}/resolve/main/onnx/model.onnx"
CONFIG_URL = f"https://huggingface.co/{HF_REPO}/resolve/main/config.json"
CLIP_FILE = MODEL_DIR / "clip_vit_b32_vision_quantized.onnx"
CLIP_URL = f"https://huggingface.co/{CLIP_REPO}/resolve/main/onnx/vision_model_quantized.onnx"
CLIP_PROMPTS_FILE = MODEL_DIR / "clip_prompt_embeddings.json"
CLIP_SIZE = 224
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
FLOOD_PROBABILITY_THRESHOLD = 0.5

INPUT_SIZE = 512
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

WATER_CLASSES = {21: "water", 26: "sea", 60: "river", 128: "lake"}
PERSON = 12
VEHICLES = {20: "car", 80: "bus", 83: "truck", 102: "van"}
BOAT = 76

MIN_OBJECT_PIXELS = 40  # on the 128 x 128 output grid


class VisionModelUnavailable(RuntimeError):
    pass


def _fetch(url: str, dest: Path, timeout: float) -> None:
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=timeout) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)


def download_model(timeout: float = 300.0) -> Path:
    """Fetch the ONNX weights and label map once (about 15 MB + 89 MB)."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if not LABELS_FILE.exists():
        with urllib.request.urlopen(CONFIG_URL, timeout=timeout) as r:
            cfg = json.load(r)
        LABELS_FILE.write_text(json.dumps(cfg["id2label"]))
    if not MODEL_FILE.exists():
        _fetch(MODEL_URL, MODEL_FILE, timeout)
    if not CLIP_FILE.exists():
        _fetch(CLIP_URL, CLIP_FILE, timeout)
    return MODEL_FILE


class FloodVisionService:
    def __init__(self) -> None:
        self._session = None
        self._clip = None
        self._prompts: Dict[str, Any] = {}
        self._labels: Dict[str, str] = {}
        self._lock = threading.Lock()
        self.last_error: Optional[str] = None

    # ---- model lifecycle -------------------------------------------------
    def is_installed(self) -> bool:
        return MODEL_FILE.exists() and LABELS_FILE.exists() and CLIP_FILE.exists() and CLIP_PROMPTS_FILE.exists()

    def status(self) -> Dict[str, Any]:
        try:
            import onnxruntime  # noqa: F401
            runtime_ok = True
        except ImportError:
            runtime_ok = False
        return {
            "model": "CLIP ViT-B/32 zero-shot flood classifier + SegFormer-B0 ADE20K segmentation, ONNX Runtime CPU",
            "source": f"huggingface.co/{CLIP_REPO}, huggingface.co/{HF_REPO}",
            "weights_present": self.is_installed(),
            "runtime_installed": runtime_ok,
            "loaded": self._session is not None,
            "ready": runtime_ok and self.is_installed(),
            "last_error": self.last_error,
        }

    def _load(self, allow_download: bool = True):
        if self._session is not None:
            return self._session
        with self._lock:
            if self._session is not None:
                return self._session
            try:
                import onnxruntime as ort
            except ImportError as e:
                raise VisionModelUnavailable("onnxruntime is not installed (pip install onnxruntime)") from e
            if not self.is_installed():
                if not allow_download:
                    raise VisionModelUnavailable("Vision model weights are missing; run scripts/download_vision_model.py")
                try:
                    download_model()
                except Exception as e:  # network blocked, offline, etc.
                    self.last_error = f"Download failed: {e}"
                    raise VisionModelUnavailable(
                        "Vision model weights are missing and could not be downloaded. "
                        "Run `python scripts/download_vision_model.py` with internet access."
                    ) from e
            self._labels = json.loads(LABELS_FILE.read_text())
            self._prompts = json.loads(CLIP_PROMPTS_FILE.read_text())
            self._prompts["matrix"] = np.array(self._prompts["embeddings"], dtype=np.float32)
            self._clip = ort.InferenceSession(str(CLIP_FILE), providers=["CPUExecutionProvider"])
            self._session = ort.InferenceSession(str(MODEL_FILE), providers=["CPUExecutionProvider"])
            self.last_error = None
            return self._session

    # ---- inference -------------------------------------------------------
    def segment(self, image) -> np.ndarray:
        """Class id per pixel on the model's 128 x 128 output grid."""
        session = self._load()
        rgb = image.convert("RGB").resize((INPUT_SIZE, INPUT_SIZE))
        x = (np.asarray(rgb, dtype=np.float32) / 255.0 - MEAN) / STD
        x = x.transpose(2, 0, 1)[None]
        logits = session.run(None, {session.get_inputs()[0].name: x})[0][0]
        return logits.argmax(0)

    def flood_probability(self, image) -> Dict[str, Any]:
        """Zero-shot CLIP: softmax over all prompts, flood probability = sum over flood prompts."""
        from PIL import Image

        self._load()
        rgb = image.convert("RGB")
        scale = CLIP_SIZE / min(rgb.width, rgb.height)
        rgb = rgb.resize((max(CLIP_SIZE, round(rgb.width * scale)), max(CLIP_SIZE, round(rgb.height * scale))), Image.BICUBIC)
        left, top = (rgb.width - CLIP_SIZE) // 2, (rgb.height - CLIP_SIZE) // 2
        rgb = rgb.crop((left, top, left + CLIP_SIZE, top + CLIP_SIZE))
        x = ((np.asarray(rgb, dtype=np.float32) / 255.0 - CLIP_MEAN) / CLIP_STD).transpose(2, 0, 1)[None]
        emb = self._clip.run(None, {"pixel_values": x})[0][0]
        emb = emb / np.linalg.norm(emb)
        logits = self._prompts["logit_scale"] * (self._prompts["matrix"] @ emb)
        probs = np.exp(logits - logits.max())
        probs /= probs.sum()
        n_flood = len(self._prompts["flood_prompts"])
        prompts = self._prompts["flood_prompts"] + self._prompts["normal_prompts"]
        best = int(np.argmax(probs))
        return {"probability": float(probs[:n_flood].sum()), "best_match": prompts[best], "best_match_score": float(probs[best])}

    def analyze(self, image_bytes: bytes, include_overlay: bool = True) -> Dict[str, Any]:
        from PIL import Image
        from scipy import ndimage

        t0 = time.perf_counter()
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
        seg = self.segment(image)
        h, w = seg.shape

        water = np.isin(seg, list(WATER_CLASSES))
        water_share = float(water.mean())
        lower_half_water = float(water[h // 2:].mean())
        # Grow the water mask slightly so an object standing in water "touches" it.
        water_near = ndimage.binary_dilation(water, iterations=2)

        objects: List[Dict[str, Any]] = []
        for class_ids, kind in [({PERSON}, "person"), (set(VEHICLES), "car"), ({BOAT}, "boat")]:
            mask = np.isin(seg, list(class_ids))
            comps, n = ndimage.label(mask)
            for i in range(1, n + 1):
                comp = comps == i
                size = int(comp.sum())
                if size < MIN_OBJECT_PIXELS:
                    continue
                ys, xs = np.nonzero(comp)
                y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
                bottom_band = np.zeros_like(comp)
                bottom_band[max(y1 - 2, 0): min(y1 + 3, h), x0: x1 + 1] = True
                touches = bool((water_near & bottom_band).sum() >= max(2, 0.3 * (x1 - x0 + 1)))
                obj: Dict[str, Any] = {
                    "type": kind,
                    "pixels": size,
                    "bbox_grid": [int(x0), int(y0), int(x1), int(y1)],
                    "in_water": touches,
                }
                objects.append(obj)

        people = [o for o in objects if o["type"] == "person"]
        vehicles = [o for o in objects if o["type"] == "car"]
        boats = [o for o in objects if o["type"] == "boat"]
        clip = self.flood_probability(image)
        flood_detected = clip["probability"] >= FLOOD_PROBABILITY_THRESHOLD
        people_in_water = sum(o["in_water"] for o in people)
        vehicles_in_water = int(sum(o["in_water"] for o in vehicles))
        severity = self._suggest_severity(flood_detected, water_share, people_in_water, vehicles_in_water, bool(boats))

        top = np.bincount(seg.ravel(), minlength=150)
        top_classes = [
            {"label": self._labels.get(str(int(k)), str(int(k))), "share": round(float(top[k] / seg.size), 3)}
            for k in np.argsort(-top)[:6] if top[k] > 0
        ]

        result: Dict[str, Any] = {
            "data_label": "PREDICTED",
            "model": "CLIP ViT-B/32 zero-shot + SegFormer-B0 ADE20K (pretrained, ONNX Runtime)",
            "flood_detected": flood_detected,
            "flood_probability": round(clip["probability"], 3),
            "closest_description": clip["best_match"],
            "water_coverage_pct": round(water_share * 100, 1),
            "water_coverage_lower_half_pct": round(lower_half_water * 100, 1),
            "people_detected": len(people),
            "people_in_water": int(people_in_water),
            "vehicles_detected": len(vehicles),
            "vehicles_in_water": vehicles_in_water,
            "boats_detected": len(boats),
            "water_depth": {
                "estimated": False,
                "reason": "Single-photo depth estimates did not hold up in testing; the reporter enters the depth.",
            },
            "suggested_severity": severity,
            "top_scene_classes": top_classes,
            "objects": objects,
            "image_size": [image.width, image.height],
            "inference_ms": round((time.perf_counter() - t0) * 1000, 1),
            "caveats": [
                "Pretrained model, not fine-tuned on flood photos.",
                "Water coverage can miss muddy brown water (labelled earth or floor) even when a flood is detected.",
                "Wet roads with thin standing water are often not marked as flood water.",
                "Water depth is not estimated from the photo.",
            ],
        }
        if include_overlay:
            result["overlay_png_base64"] = self._overlay(image, seg)
        return result

    @staticmethod
    def _suggest_severity(flood: bool, water_share: float, people_in_water: int, vehicles_in_water: int, boats: bool) -> str:
        """Advisory only: the operator confirms severity when verifying the incident."""
        if not flood:
            return "LOW"
        if people_in_water >= 3 or (people_in_water >= 1 and water_share >= 0.4):
            return "CRITICAL"
        if people_in_water >= 1 or boats or vehicles_in_water >= 1 or water_share >= 0.5:
            return "HIGH"
        return "MODERATE"

    @staticmethod
    def _overlay(image, seg: np.ndarray) -> str:
        """Small PNG of the photo with water in blue, people in red and vehicles in yellow."""
        from PIL import Image

        base = image.convert("RGB").resize((256, int(256 * image.height / max(image.width, 1))))
        colour = np.zeros(seg.shape + (4,), dtype=np.uint8)
        colour[np.isin(seg, list(WATER_CLASSES))] = (30, 144, 255, 120)
        colour[seg == PERSON] = (239, 68, 68, 170)
        colour[np.isin(seg, list(VEHICLES))] = (250, 204, 21, 150)
        colour[seg == BOAT] = (16, 185, 129, 170)
        mask = Image.fromarray(colour, "RGBA").resize(base.size, Image.NEAREST)
        out = base.convert("RGBA")
        out.alpha_composite(mask)
        buf = io.BytesIO()
        out.convert("RGB").save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")


flood_vision_service = FloodVisionService()
