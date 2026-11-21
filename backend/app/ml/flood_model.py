import csv
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
MODEL_FILE = ARTIFACTS_DIR / "flood_rf_model.joblib"
METRICS_FILE = ARTIFACTS_DIR / "flood_model_metrics.joblib"

EVALUATION_VERSION = 2

# The dataset label is defined as water_level_m > 4.21 m, so a model that is given the water level
# can reproduce the label exactly (100% accuracy) without learning anything. The served model
# therefore predicts flood risk from weather only (an early warning, before the gauge rises), and
# the water level is applied separately as a transparent gauge rule.
ALL_FEATURES = ["rainfall_mm", "water_level_m", "humidity_pct", "temperature_c"]
MODEL_FEATURES = ["rainfall_mm", "humidity_pct", "temperature_c"]
LABEL_THRESHOLD_M = 4.21


def _new_forest() -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42, class_weight="balanced")


def _scores(y_true, y_pred, y_prob) -> Dict[str, Any]:
    from sklearn.metrics import confusion_matrix

    try:
        auc = float(roc_auc_score(y_true, y_prob))
    except ValueError:
        auc = float("nan")
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1_score": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(auc, 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
    }


def _cv_scores(X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
    from sklearn.model_selection import StratifiedKFold

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    accs, f1s, aucs, recs = [], [], [], []
    for tr, va in skf.split(X, y):
        m = _new_forest().fit(X[tr], y[tr])
        pred = m.predict(X[va])
        prob = m.predict_proba(X[va])[:, 1]
        accs.append(accuracy_score(y[va], pred))
        f1s.append(f1_score(y[va], pred, zero_division=0))
        recs.append(recall_score(y[va], pred, zero_division=0))
        aucs.append(roc_auc_score(y[va], prob))
    r = lambda v: round(float(v), 4)
    return {
        "accuracy_mean": r(np.mean(accs)), "accuracy_std": r(np.std(accs)),
        "f1_mean": r(np.mean(f1s)), "recall_mean": r(np.mean(recs)), "roc_auc_mean": r(np.mean(aucs)),
    }


def load_dataset() -> Tuple[np.ndarray, np.ndarray, Path]:
    """Rows in file order with columns ALL_FEATURES, and the 0/1 flood label."""
    from app.core.config import settings

    csv_path = settings.CLEAN_DATASET_DIR / "clean_flood_prediction_data.csv"
    if not csv_path.exists():
        alt_path = Path("flood pred detc rescue net clean dataset/clean_flood_prediction_data.csv")
        if alt_path.exists():
            csv_path = alt_path
    X, y = [], []
    if csv_path.exists():
        with open(csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
            for row in csv.DictReader(f):
                try:
                    X.append([float(row[c]) for c in ALL_FEATURES])
                    y.append(int(float(row["flood_risk_label"])))
                except (ValueError, KeyError):
                    continue
    X, y = np.array(X), np.array(y)
    if len(X) < 50:
        raise ValueError(f"Insufficient samples in {csv_path} to train flood model")
    return X, y, csv_path


def run_evaluation_suite(X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
    """Four checks that show what the model can and cannot do on this dataset."""
    idx = [ALL_FEATURES.index(f) for f in MODEL_FEATURES]
    rng = np.random.default_rng(7)
    suite: Dict[str, Any] = {}

    suite["leaky_baseline_all_features"] = {
        "description": "All four inputs including water level. The label is water_level_m > 4.21 m, so this score is label leakage, not skill.",
        **_cv_scores(X, y),
    }
    suite["early_warning_weather_only"] = {
        "description": "Served model. Rainfall, humidity and temperature only, i.e. before the gauge reading is known.",
        **_cv_scores(X[:, idx], y),
    }
    noisy = X.copy()
    noisy[:, 1] += rng.normal(0.0, 0.5, len(X))
    suite["gauge_noise_0_5m"] = {
        "description": "All inputs, with Gaussian noise (sd 0.5 m) on the water level to mimic an imperfect field gauge.",
        **_cv_scores(noisy, y),
    }
    suite["next_hour_forecast"] = {
        "description": "Predict the label one hour ahead from the current hour. Rows are nearly independent "
                       "(lag-1 autocorrelation of water level about 0.03), so this is close to chance: the "
                       "dataset cannot support a true time-series forecast.",
        "lag1_autocorrelation_water_level": round(float(np.corrcoef(X[:-1, 1], X[1:, 1])[0, 1]), 4),
        **_cv_scores(X[:-1], y[1:]),
    }
    return suite


class FloodModelService:
    def __init__(self):
        self.model: Any = None
        self.metrics: Dict[str, Any] = {}
        self.feature_names = list(MODEL_FEATURES)
        self._load_or_train()

    def _load_or_train(self):
        if MODEL_FILE.exists() and METRICS_FILE.exists():
            try:
                model = joblib.load(MODEL_FILE)
                metrics = joblib.load(METRICS_FILE)
                if metrics.get("evaluation_version") == EVALUATION_VERSION:
                    self.model, self.metrics = model, metrics
                    return
            except Exception as e:
                print(f"[FloodModelService] Error loading model, retraining: {e}")
        self.train_model()

    def train_model(self) -> Dict[str, Any]:
        X_all, y, csv_path = load_dataset()
        idx = [ALL_FEATURES.index(f) for f in MODEL_FEATURES]
        X = X_all[:, idx]

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
        rf = _new_forest().fit(X_train, y_train)
        holdout = _scores(y_test, rf.predict(X_test), rf.predict_proba(X_test)[:, 1])
        cv = _cv_scores(X, y)

        # Chronological holdout: first 800 rows train, last 200 rows test.
        rf_time = _new_forest().fit(X[:800], y[:800])
        chrono = _scores(y[800:], rf_time.predict(X[800:]), rf_time.predict_proba(X[800:])[:, 1])

        self.metrics = {
            "evaluation_version": EVALUATION_VERSION,
            "model_architecture": "RandomForestClassifier(n_estimators=100, max_depth=6, class_weight=balanced)",
            "model_inputs": list(MODEL_FEATURES),
            "training_samples": int(len(X_train)),
            "test_samples": int(len(X_test)),
            **holdout,
            "cv_5fold_accuracy_mean": cv["accuracy_mean"],
            "cv_5fold_accuracy_std": cv["accuracy_std"],
            "cv_5fold_f1_mean": cv["f1_mean"],
            "cv_5fold_recall_mean": cv["recall_mean"],
            "cv_5fold_roc_auc_mean": cv["roc_auc_mean"],
            "chronological_holdout_accuracy": chrono["accuracy"],
            "chronological_confusion_matrix": chrono["confusion_matrix"],
            "class_distribution": {
                "total_records": int(len(y)),
                "non_flood_class_0": int(np.sum(y == 0)),
                "flood_class_1": int(np.sum(y == 1)),
                "flood_prevalence_pct": round(float(np.mean(y) * 100), 1),
            },
            "feature_importances": {
                name: round(float(imp), 4) for name, imp in zip(MODEL_FEATURES, rf.feature_importances_)
            },
            "dataset_source": "flood pred detc rescue net clean dataset/clean_flood_prediction_data.csv",
            "is_trained_on_real_data": True,
            "evaluation_suite": run_evaluation_suite(X_all, y),
            "validation_audit": {
                "target_label_rule": f"Label is 1 exactly when water_level_m > {LABEL_THRESHOLD_M} m",
                "leakage_handling": "Water level is excluded from the model inputs; it is applied as a separate gauge rule",
                "forecast_horizons_type": "Physical runoff surge formula projection (not multi-step ML forecast)",
                "known_limitation": "Rows are nearly independent hours, so next-hour forecasting is near chance on this dataset",
            },
        }

        self.model = rf
        joblib.dump(rf, MODEL_FILE)
        joblib.dump(self.metrics, METRICS_FILE)
        return self.metrics

    def predict(
        self,
        rainfall_mm: float,
        water_level_m: float,
        humidity_pct: float = 80.0,
        temperature_c: float = 28.0,
    ) -> Dict[str, Any]:
        if self.model is None:
            self._load_or_train()

        features = np.array([[rainfall_mm, humidity_pct, temperature_c]])
        prob = float(self.model.predict_proba(features)[0, 1])
        gauge_flood = water_level_m > LABEL_THRESHOLD_M

        # Risk level combines the weather model with the transparent gauge rule.
        if prob >= 0.75 or water_level_m >= 5.5:
            risk_level = "CRITICAL"
            advisory = "Severe inundation imminent. Immediate low-lying evacuation and rescue dispatch recommended."
        elif prob >= 0.50 or water_level_m >= 3.8:
            risk_level = "HIGH"
            advisory = "High flood probability. Alert local disaster management teams and stage rescue assets."
        elif prob >= 0.25 or water_level_m >= 2.5:
            risk_level = "MODERATE"
            advisory = "Elevated runoff conditions. Continuous telemetry monitoring required."
        else:
            risk_level = "LOW"
            advisory = "Water levels within normal drainage capacity. Standard monitoring active."

        # Compute dynamic forecast horizons (+30m, +45m, +60m)
        # Based on physical hydrology accumulation rate: delta_water = rainfall * runoff_coeff
        runoff_surge = (rainfall_mm / 100.0) * 0.15
        h30_prob = min(0.99, max(0.01, prob + runoff_surge * 0.5))
        h45_prob = min(0.99, max(0.01, prob + runoff_surge * 0.9))
        h60_prob = min(0.99, max(0.01, prob + runoff_surge * 1.3))

        # Contributing factor breakdown
        importances = self.metrics.get("feature_importances", {})
        rain_wt = importances.get("rainfall_mm", 0.0)
        wl_wt = 0.0  # gauge rule, not a model input
        hum_wt = importances.get("humidity_pct", 0.0)
        temp_wt = importances.get("temperature_c", 0.0)

        factors = [
            {
                "factor": "Current Water Level",
                "impact": f"{water_level_m:.1f} m ({'Above' if gauge_flood else 'Within'} the {LABEL_THRESHOLD_M} m flood threshold; gauge rule, not a model input)",
                "weight": wl_wt,
            },
            {
                "factor": "Rainfall Intensity",
                "impact": f"{rainfall_mm:.1f} mm/hr ({'Intense storm' if rainfall_mm > 35 else 'Moderate' if rainfall_mm > 15 else 'Light'})",
                "weight": rain_wt,
            },
            {
                "factor": "Atmospheric Humidity",
                "impact": f"{humidity_pct:.0f}% saturation",
                "weight": hum_wt,
            },
            {
                "factor": "Ambient Temperature",
                "impact": f"{temperature_c:.1f}°C",
                "weight": temp_wt,
            },
        ]

        return {
            "risk_level": risk_level,
            "probability": round(prob, 3),
            "horizon_30m": round(h30_prob, 3),
            "horizon_45m": round(h45_prob, 3),
            "horizon_60m": round(h60_prob, 3),
            "confidence_level": (
                f"Early-warning model, 5-fold CV accuracy {self.metrics.get('cv_5fold_accuracy_mean', 0) * 100:.1f}% "
                f"(F1 {self.metrics.get('cv_5fold_f1_mean', 0):.2f})"
            ),
            "gauge_rule_triggered": bool(gauge_flood),
            "contributing_factors": factors,
            "model_name": "Random Forest Early-Warning Flood Risk Model (weather inputs)",
            "is_simulated": False,
            "data_source": "clean_flood_prediction_data.csv (1000 real sensor telemetry records)",
            "evaluation_metrics": self.metrics,
            "advisory": advisory,
        }

flood_ml_service = FloodModelService()
