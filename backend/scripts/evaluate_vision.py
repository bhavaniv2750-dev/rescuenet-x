"""Measure the flood-photo detector.

1. Detection rate on the project's flood/ folder (every photo shows a flood).
2. Optional external check on labelled photos from FloodIT (Apache-2.0,
   huggingface.co/datasets/muhan-yy/FloodIT): folders flood_is / flood_no.
3. Optional false-alarm check on non-flood scenes: a folder with one sub-folder
   per scene type (we used 50 random test photos each of buildings, forest,
   glacier, mountain, sea and street from the Intel Image Classification set).

Each photo is scored by the served rule (CLIP flood probability >= 0.5) and,
for comparison, by a SegFormer-only rule (water coverage >= 5%).

Usage (from backend/):  python scripts/evaluate_vision.py [--floodit DIR] [--negatives DIR]
Writes the numbers to stdout as JSON.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.vision_service import flood_vision_service  # noqa: E402

EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def run_folder(folder: Path):
    rows = []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in EXTS:
            continue
        r = flood_vision_service.analyze(p.read_bytes(), include_overlay=False)
        rows.append({"file": p.name, "flood": r["flood_detected"], "seg_flood": r["water_coverage_pct"] >= 5.0,
                     "p": r["flood_probability"], "water_pct": r["water_coverage_pct"],
                     "people_in_water": r["people_in_water"], "vehicles_in_water": r["vehicles_in_water"],
                     "severity": r["suggested_severity"], "ms": r["inference_ms"]})
    return rows


def summary(rows):
    n = len(rows)
    det = sum(r["flood"] for r in rows)
    sev = {}
    for r in rows:
        sev[r["severity"]] = sev.get(r["severity"], 0) + 1
    ms = sorted(r["ms"] for r in rows)
    return {
        "images": n,
        "flagged_flood": det,
        "flagged_pct": round(100 * det / n, 1) if n else None,
        "segformer_only_flagged_pct": round(100 * sum(r["seg_flood"] for r in rows) / n, 1) if n else None,
        "median_water_pct": sorted(r["water_pct"] for r in rows)[n // 2] if n else None,
        "with_people_in_water": sum(r["people_in_water"] > 0 for r in rows),
        "with_vehicles_in_water": sum(r["vehicles_in_water"] > 0 for r in rows),
        "suggested_severity": sev,
        "median_inference_ms": ms[n // 2] if n else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floodit", type=Path, help="folder holding FloodIT flood_is/ and flood_no/")
    ap.add_argument("--negatives", type=Path, help="folder of non-flood scene sub-folders")
    args = ap.parse_args()
    t = time.time()
    out = {"model": flood_vision_service.status()["model"], "threshold": "CLIP flood probability >= 0.5 (SegFormer-only comparison: water coverage >= 5%)"}
    flood_rows = run_folder(settings.FLOOD_IMG_DIR)
    out["project_flood_folder"] = summary(flood_rows)
    out["project_missed_files"] = [r["file"] for r in flood_rows if not r["flood"]]
    if args.floodit:
        pos, neg = run_folder(args.floodit / "flood_is"), run_folder(args.floodit / "flood_no")
        tp = sum(r["flood"] for r in pos); fn = len(pos) - tp
        fp = sum(r["flood"] for r in neg); tn = len(neg) - fp
        out["floodit_external"] = {
            "flood_images": len(pos), "non_flood_images": len(neg),
            "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "accuracy": round((tp + tn) / max(len(pos) + len(neg), 1), 3),
            "false_alarms": [r["file"] for r in neg if r["flood"]],
        }
    if args.negatives:
        per = {}
        allneg = []
        for sub in sorted(d for d in args.negatives.iterdir() if d.is_dir()):
            rows = run_folder(sub)
            allneg += rows
            per[sub.name] = {"images": len(rows), "false_alarms": sum(r["flood"] for r in rows),
                             "segformer_only_false_alarms": sum(r["seg_flood"] for r in rows)}
        n = len(allneg)
        out["non_flood_scenes"] = {
            "images": n,
            "false_alarms": sum(r["flood"] for r in allneg),
            "false_alarm_pct": round(100 * sum(r["flood"] for r in allneg) / max(n, 1), 1),
            "segformer_only_false_alarm_pct": round(100 * sum(r["seg_flood"] for r in allneg) / max(n, 1), 1),
            "by_scene": per,
            "false_alarm_files": [r["file"] for r in allneg if r["flood"]],
        }
        pos = flood_rows
        tp = sum(r["flood"] for r in pos); fp = out["non_flood_scenes"]["false_alarms"]
        fn, tn = len(pos) - tp, n - fp
        prec = tp / max(tp + fp, 1); rec = tp / max(len(pos), 1)
        out["combined_project_vs_non_flood"] = {
            "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "accuracy": round((tp + tn) / max(len(pos) + n, 1), 3),
            "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(2 * prec * rec / max(prec + rec, 1e-9), 3),
            "specificity": round(tn / max(n, 1), 3),
        }
    out["seconds"] = round(time.time() - t, 1)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
