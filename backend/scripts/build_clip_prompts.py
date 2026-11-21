"""Encode the flood / non-flood text prompts once with the CLIP text model.

The app only ships the resulting 512-number vectors (clip_prompt_embeddings.json),
so it never needs the 64 MB text model or a tokenizer at runtime.

Usage (from backend/): python scripts/build_clip_prompts.py CLIP_DIR
CLIP_DIR holds tokenizer.json and onnx/text_model_quantized.onnx from
huggingface.co/Xenova/clip-vit-base-patch32 (MIT licence).
"""

import json
import sys
from pathlib import Path

import numpy as np

FLOOD_PROMPTS = [
    "a photo of a flooded street",
    "a photo of a flooded town",
    "a photo of people wading through flood water",
    "a photo of cars submerged in flood water",
    "a photo of muddy flood water flowing through a street",
    "a photo of houses surrounded by flood water",
    "an aerial photo of a flooded area",
    "a photo of a rescue boat in a flooded street",
]
NORMAL_PROMPTS = [
    "a photo of a dry street",
    "a photo of a wet road after rain",
    "a photo of a city street",
    "a photo of buildings",
    "a photo of a river flowing normally between its banks",
    "a photo of the sea",
    "a photo of a lake",
    "a photo of a forest",
    "a photo of mountains",
    "a photo of a beach",
]

OUT = Path(__file__).resolve().parent.parent / "app" / "ml" / "artifacts" / "vision" / "clip_prompt_embeddings.json"


def main(clip_dir: Path) -> None:
    import onnxruntime as ort
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(str(clip_dir / "tokenizer.json"))
    tok.enable_padding(length=77, pad_id=49407)
    tok.enable_truncation(max_length=77)
    sess = ort.InferenceSession(str(clip_dir / "onnx" / "text_model_quantized.onnx"), providers=["CPUExecutionProvider"])
    prompts = FLOOD_PROMPTS + NORMAL_PROMPTS
    ids = np.array([e.ids for e in tok.encode_batch(prompts)], dtype=np.int64)
    emb = sess.run(None, {"input_ids": ids})[0]
    emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "model": "Xenova/clip-vit-base-patch32 (text_model_quantized)",
        "logit_scale": 100.0,
        "flood_prompts": FLOOD_PROMPTS,
        "normal_prompts": NORMAL_PROMPTS,
        "embeddings": np.round(emb, 6).tolist(),
    }))
    print(f"wrote {OUT} ({len(prompts)} prompts)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
