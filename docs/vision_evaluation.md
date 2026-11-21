# Flood photo analysis: evaluation

## Models (pretrained, used as published, no fine-tuning)

| Job | Model | Size | Licence |
|---|---|---|---|
| Flood yes/no | CLIP ViT-B/32 vision encoder, zero-shot (Xenova ONNX export, quantized) | 89 MB | MIT |
| Where the water is; people, vehicles and boats in water | SegFormer-B0 fine-tuned on ADE20K (Xenova ONNX export) | 15 MB | NVIDIA SegFormer licence (research use) |

Both run on the CPU through ONNX Runtime, taking about 190 ms per photo. The weights are not stored in git.
They download on first use or with `python scripts/download_vision_model.py`.

**Flood decision:** the photo is compared with 8 flood prompts ("a photo of a flooded street", "a photo of
muddy flood water flowing through a street", ...) and 10 normal prompts ("a photo of a dry street",
"a photo of a wet road after rain", "a photo of the sea", ...). Flood probability is the softmax share of
the flood prompts. A flood is flagged when it is 0.5 or more. **The prompts and the threshold were fixed
before any scoring and were not tuned on the test photos.**

## Results (`python scripts/evaluate_vision.py --floodit DIR --negatives DIR`)

| Test set | Photos | Served model (CLIP) | SegFormer only (water at least 5%) |
|---|---|---|---|
| Project `flood/` folder (all floods): detection rate | 809 | **99.3%** (803) | 76.6% (620) |
| Non-flood scenes (Intel Image Classification, 50 each of 6 types): false alarms | 300 | **7.3%** (22) | 24.3% (73) |
| of which sea | 50 | 3 | 47 |
| of which street | 50 | 9 | 0 |
| of which buildings | 50 | 6 | 4 |
| of which glacier / mountain / forest | 150 | 3 / 1 / 0 | 14 / 7 / 1 |

Combined (809 flood + 300 non-flood): accuracy **97.5%**, precision 97.3%, recall 99.3%, F1 0.983,
specificity 92.7%. Accuracy depends on the 809:300 mix, so recall and specificity are the fairer
numbers to quote.

FloodIT external sample (Apache-2.0, only 10 photos are public): 5 of 5 floods found, but 4 of 5
"non-flood" photos were flagged. Those photos are flood-related posts (a flood-supplies warehouse,
responders gathering, a rainfall map), and 10 photos are too few to draw conclusions from.

## What the model gets wrong

- **False alarms** come from water beside buildings (canals, harbours), glaciers above water and some
  street scenes. One indoor room was also flagged.
- **SegFormer under-measures muddy water.** It often labels brown floodwater as earth or floor, so the water
  coverage figure can be low even when CLIP correctly says "flood".
- **Water depth is not estimated.** Two single-photo methods were tried: (1) the height-to-width ratio of a
  person or car standing in water, and (2) whether the object's outline is cut flat by the waterline.
  Neither separated shallow from deep water on our photos. For example, a car sunk to its bumper scored
  as "ankle" depth, and seated people as "chest" depth. The reporter now enters the depth band instead
  (`reported_water_depth`: ANKLE, KNEE, WAIST, CHEST_OR_DEEPER, UNKNOWN).
- The non-flood photos are small (150 x 150 px) and were not taken in Bengaluru, so real-world false-alarm
  rates may differ.

All photo results are labelled **PREDICTED** and only suggest a severity. The operator confirms it when
verifying the incident.
