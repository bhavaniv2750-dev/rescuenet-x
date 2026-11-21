# Flood risk model: honest evaluation

Dataset: `clean_flood_prediction_data.csv`, 1,000 hourly rows, 216 flood hours (21.6%).
Model: Random Forest, 100 trees, max depth 6, balanced class weights, random state 42.

## Why the earlier score was 100%

The label is defined as `water_level_m > 4.21 m`. A model that is given the water level can rebuild
the label exactly, so 100% accuracy measures label leakage, not skill. The served model therefore
uses **rainfall, humidity and temperature only**. That makes it an early warning that works before the gauge
rises. The water level is still used, but as a separate, transparent gauge rule.

## Served model (weather inputs)

| Metric | Value |
|---|---|
| Held-out accuracy (200 rows, 80/20 stratified split) | **97.0%** |
| Precision / Recall / F1 | 0.911 / 0.954 / 0.932 |
| ROC-AUC | 0.994 |
| Confusion matrix (TN, FP, FN, TP) | 153, 4, 2, 41 |
| 5-fold stratified CV accuracy | **97.5% ± 0.6%** |
| 5-fold CV F1 | 0.943 |
| Chronological holdout (train first 800, test last 200) | 97.5% |
| Feature importance | rainfall 0.88, humidity 0.06, temperature 0.06 |

On the held-out set the model makes 6 mistakes out of 200: 4 false alarms and 2 missed floods.

## Evaluation suite (5-fold CV)

| Test | Accuracy | F1 | ROC-AUC | Meaning |
|---|---|---|---|---|
| All inputs incl. water level | 100.0% | 1.00 | 1.00 | Leakage; not a valid score |
| Early warning, weather only (served) | 97.5% | 0.94 | 0.99 | Realistic score |
| All inputs, gauge noise sd 0.5 m | 97.5% | 0.94 | 1.00 | Robust to an imperfect gauge |
| Next-hour forecast | 61.6% | 0.25 | 0.51 | Near chance |

## Limitations

- The rows are nearly independent hours (lag-1 autocorrelation of water level is 0.03), so the dataset
  cannot support a true time-series forecast. The +30/+45/+60 minute values are runoff-formula
  projections, not machine-learning forecasts.
- The data comes from one station, so performance on other catchments is untested.

The numbers are recomputed whenever the model is trained (`FloodModelService.train_model`) and are served
at `/api/datasets/models` and in every `/api/flood/forecast` response.
