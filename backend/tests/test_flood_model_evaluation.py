"""The served flood model must not see the water level, because the label is defined from it."""

from app.ml.flood_model import LABEL_THRESHOLD_M, flood_ml_service


def test_water_level_is_not_a_model_input():
    assert "water_level_m" not in flood_ml_service.metrics["model_inputs"]
    assert flood_ml_service.model.n_features_in_ == 3


def test_reported_accuracy_is_realistic_not_perfect():
    m = flood_ml_service.metrics
    assert 0.90 <= m["accuracy"] < 1.0
    assert 0.90 <= m["cv_5fold_accuracy_mean"] < 1.0
    assert m["cv_5fold_accuracy_std"] > 0


def test_evaluation_suite_documents_leakage_and_limits():
    suite = flood_ml_service.metrics["evaluation_suite"]
    assert suite["leaky_baseline_all_features"]["accuracy_mean"] == 1.0
    assert suite["early_warning_weather_only"]["accuracy_mean"] < 1.0
    assert suite["next_hour_forecast"]["roc_auc_mean"] < 0.65  # near chance, stated as a limitation


def test_gauge_rule_is_applied_separately():
    high = flood_ml_service.predict(rainfall_mm=2.0, water_level_m=LABEL_THRESHOLD_M + 1.5, humidity_pct=60, temperature_c=30)
    assert high["gauge_rule_triggered"] is True
    assert high["risk_level"] == "CRITICAL"
    low = flood_ml_service.predict(rainfall_mm=2.0, water_level_m=1.0, humidity_pct=60, temperature_c=30)
    assert low["gauge_rule_triggered"] is False
