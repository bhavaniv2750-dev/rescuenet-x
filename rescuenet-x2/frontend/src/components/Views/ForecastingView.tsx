import React, { useState } from 'react';
import { api } from '../../api/client';
import type { FloodPredictionResult } from '../../api/types';
import { Activity, Sliders, TrendingUp, CheckCircle2 } from 'lucide-react';

interface ForecastingViewProps {
  initialForecast?: FloodPredictionResult | null;
}

const SUITE_LABELS: Record<string, string> = {
  leaky_baseline_all_features: 'All inputs incl. water level (leakage)',
  early_warning_weather_only: 'Early warning, weather only (served)',
  gauge_noise_0_5m: 'Noisy gauge, sd 0.5 m',
  next_hour_forecast: 'Next-hour forecast',
};

export const ForecastingView: React.FC<ForecastingViewProps> = ({ initialForecast }) => {
  // Input Sliders State
  const [rainfall, setRainfall] = useState<number>(38.0);
  const [waterLevel, setWaterLevel] = useState<number>(4.2);
  const [humidity, setHumidity] = useState<number>(85.0);
  const [temperature, setTemperature] = useState<number>(27.0);

  // Results State
  const [forecast, setForecast] = useState<FloodPredictionResult | null>(initialForecast || null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleSimulate = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.predictFlood({
        rainfall_mm: rainfall,
        water_level_m: waterLevel,
        humidity_pct: humidity,
        temperature_c: temperature,
      });
      setForecast(res);
    } catch (err: any) {
      setError(err.message || 'Error executing flood prediction scenario');
    } finally {
      setLoading(false);
    }
  };

  const applyPreset = (r: number, w: number, h: number, t: number) => {
    setRainfall(r);
    setWaterLevel(w);
    setHumidity(h);
    setTemperature(t);
  };

  return (
    <div className="forecasting-container">
      <div className="view-header">
        <div>
          <h2>AI Flood Risk Forecaster & Scenario Simulator</h2>
          <p>
            Powered by a validated RandomForest ML Classifier trained on 1,000 real-world sensor telemetry records
            from <code>clean_flood_prediction_data.csv</code>.
          </p>
        </div>
        <div className="preset-buttons">
          <span className="text-muted" style={{ fontSize: '12px', marginRight: '6px' }}>Presets:</span>
          <button className="btn-secondary btn-sm" onClick={() => applyPreset(8.0, 1.8, 65.0, 30.0)}>
            Light Monsoon
          </button>
          <button className="btn-secondary btn-sm" onClick={() => applyPreset(42.0, 4.5, 88.0, 26.0)}>
            Storm Surge
          </button>
          <button className="btn-secondary btn-sm" onClick={() => applyPreset(95.0, 7.2, 98.0, 23.0)}>
            Severe Cloudburst
          </button>
        </div>
      </div>

      {error && <div className="notice-banner banner-error">{error}</div>}

      <div className="forecasting-grid">
        {/* Scenario Input Controls Card */}
        <div className="panel scenario-card">
          <div className="panel-title-bar">
            <div>
              <h3>Hydrological & Weather Inputs</h3>
              <p>Adjust environmental telemetry to test downstream inundation probability</p>
            </div>
            <Sliders size={18} className="text-cyan" />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSimulate();
            }}
            className="scenario-form"
          >
            {/* Rainfall Slider */}
            <div className="slider-group">
              <div className="slider-label">
                <span>Rainfall Intensity</span>
                <span className="slider-value font-mono text-cyan">{rainfall.toFixed(1)} mm/hr</span>
              </div>
              <input
                type="range"
                min="0"
                max="120"
                step="0.5"
                value={rainfall}
                onChange={(e) => setRainfall(parseFloat(e.target.value))}
                className="range-slider"
              />
              <div className="slider-hints">
                <span>0 mm (Dry)</span>
                <span>35 mm (Heavy)</span>
                <span>120 mm (Extreme Cloudburst)</span>
              </div>
            </div>

            {/* Water Level Slider */}
            <div className="slider-group">
              <div className="slider-label">
                <span>River / Drainage Water Level</span>
                <span className="slider-value font-mono text-cyan">{waterLevel.toFixed(1)} meters</span>
              </div>
              <input
                type="range"
                min="0"
                max="10"
                step="0.1"
                value={waterLevel}
                onChange={(e) => setWaterLevel(parseFloat(e.target.value))}
                className="range-slider"
              />
              <div className="slider-hints">
                <span>0 m (Empty)</span>
                <span>3.0 m (Warning)</span>
                <span>5.5+ m (Danger / Breach)</span>
              </div>
            </div>

            {/* Humidity Slider */}
            <div className="slider-group">
              <div className="slider-label">
                <span>Atmospheric Relative Humidity</span>
                <span className="slider-value font-mono text-cyan">{humidity.toFixed(0)}%</span>
              </div>
              <input
                type="range"
                min="20"
                max="100"
                step="1"
                value={humidity}
                onChange={(e) => setHumidity(parseFloat(e.target.value))}
                className="range-slider"
              />
              <div className="slider-hints">
                <span>20% (Dry Air)</span>
                <span>80% (Saturated)</span>
                <span>100% (Dense Fog/Rain)</span>
              </div>
            </div>

            {/* Temperature Slider */}
            <div className="slider-group">
              <div className="slider-label">
                <span>Ambient Air Temperature</span>
                <span className="slider-value font-mono text-cyan">{temperature.toFixed(1)}°C</span>
              </div>
              <input
                type="range"
                min="10"
                max="45"
                step="0.5"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="range-slider"
              />
              <div className="slider-hints">
                <span>10°C (Cold Front)</span>
                <span>28°C (Normal)</span>
                <span>45°C (Heatwave)</span>
              </div>
            </div>

            <button type="submit" className="btn-primary btn-block" disabled={loading}>
              {loading ? 'Evaluating Model Inferences...' : '▶ Compute AI Flood Forecast'}
            </button>
          </form>
        </div>

        {/* Prediction Results & Explanation Card */}
        <div className="panel results-card">
          <div className="panel-title-bar">
            <div>
              <h3>AI Inference & Multi-Horizon Projections</h3>
              <p>Model Confidence: {forecast?.confidence_level || 'run a scenario to see the model evaluation'}</p>
            </div>
            <TrendingUp size={18} className="text-emerald" />
          </div>

          {forecast ? (
            <div className="prediction-content">
              {/* Main Risk Status Box */}
              <div className={`risk-result-banner risk-${forecast.risk_level.toLowerCase()}`}>
                <div className="risk-banner-left">
                  <div className="risk-tag">CLASSIFIED FLOOD RISK</div>
                  <div className="risk-title">{forecast.risk_level}</div>
                  <p className="risk-advisory">{forecast.advisory}</p>
                </div>
                <div className="risk-prob-circle">
                  <span className="prob-big">{Math.round(forecast.probability * 100)}%</span>
                  <span className="prob-label">Calibrated Score</span>
                </div>
              </div>

              {/* Forecast Horizon Progress Bars (+30m, +45m, +60m) */}
              <div className="horizons-container">
                <h4>Dynamic Flood Horizon Outlook (Hydrological Runoff Surge Scenarios)</h4>
                <div className="horizon-bar-item">
                  <div className="horizon-meta">
                    <span>+30 Minutes Projection</span>
                    <span className="font-mono">{Math.round(forecast.horizon_30m * 100)}% probability</span>
                  </div>
                  <div className="progress-track">
                    <div
                      className="progress-fill"
                      style={{
                        width: `${Math.round(forecast.horizon_30m * 100)}%`,
                        backgroundColor: forecast.horizon_30m > 0.7 ? '#ef4444' : forecast.horizon_30m > 0.4 ? '#f97316' : '#eab308',
                      }}
                    />
                  </div>
                </div>

                <div className="horizon-bar-item">
                  <div className="horizon-meta">
                    <span>+45 Minutes Projection</span>
                    <span className="font-mono">{Math.round(forecast.horizon_45m * 100)}% probability</span>
                  </div>
                  <div className="progress-track">
                    <div
                      className="progress-fill"
                      style={{
                        width: `${Math.round(forecast.horizon_45m * 100)}%`,
                        backgroundColor: forecast.horizon_45m > 0.7 ? '#ef4444' : forecast.horizon_45m > 0.4 ? '#f97316' : '#eab308',
                      }}
                    />
                  </div>
                </div>

                <div className="horizon-bar-item">
                  <div className="horizon-meta">
                    <span>+60 Minutes Projection</span>
                    <span className="font-mono">{Math.round(forecast.horizon_60m * 100)}% probability</span>
                  </div>
                  <div className="progress-track">
                    <div
                      className="progress-fill"
                      style={{
                        width: `${Math.round(forecast.horizon_60m * 100)}%`,
                        backgroundColor: forecast.horizon_60m > 0.7 ? '#ef4444' : forecast.horizon_60m > 0.4 ? '#f97316' : '#eab308',
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Contributing Features */}
              <div className="factors-section">
                <h4>Contributing Feature Weights (Gini Importance)</h4>
                <div className="factors-grid">
                  {forecast.contributing_factors.map((f) => (
                    <div key={f.factor} className="factor-pill">
                      <div className="factor-name">{f.factor}</div>
                      <div className="factor-impact">{f.impact}</div>
                      <div className="factor-wt font-mono">Weight: {(f.weight * 100).toFixed(1)}%</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Model Validation & Evaluation Card */}
              <div className="metrics-box">
                <div className="metrics-header">
                  <CheckCircle2 size={16} className="text-emerald" />
                  <strong>Empirical Machine Learning Validation & Audit Metrics</strong>
                </div>
                <div className="metrics-row">
                  <div><strong>Holdout Acc:</strong> {(forecast.evaluation_metrics.accuracy * 100).toFixed(1)}%</div>
                  {forecast.evaluation_metrics.cv_5fold_accuracy_mean !== undefined && (
                    <div><strong>5-Fold CV:</strong> {(forecast.evaluation_metrics.cv_5fold_accuracy_mean * 100).toFixed(1)}% (±{((forecast.evaluation_metrics.cv_5fold_accuracy_std ?? 0) * 100).toFixed(1)}%)</div>
                  )}
                  <div><strong>Precision:</strong> {(forecast.evaluation_metrics.precision * 100).toFixed(1)}%</div>
                  <div><strong>Recall:</strong> {(forecast.evaluation_metrics.recall * 100).toFixed(1)}%</div>
                  <div><strong>ROC-AUC:</strong> {forecast.evaluation_metrics.roc_auc.toFixed(3)}</div>
                  <div><strong>Holdout Test:</strong> {forecast.evaluation_metrics.test_samples} samples</div>
                </div>
                {forecast.evaluation_metrics.confusion_matrix && (
                  <div style={{ marginTop: '8px', padding: '6px 10px', background: 'rgba(15, 23, 42, 0.4)', borderRadius: '6px', fontSize: '11px', display: 'flex', gap: '16px', alignItems: 'center' }}>
                    <span style={{ color: '#38bdf8', fontWeight: 600 }}>Confusion Matrix (Holdout):</span>
                    <span className="font-mono">TN: {forecast.evaluation_metrics.confusion_matrix[0][0]}</span>
                    <span className="font-mono">FP: {forecast.evaluation_metrics.confusion_matrix[0][1]}</span>
                    <span className="font-mono">FN: {forecast.evaluation_metrics.confusion_matrix[1][0]}</span>
                    <span className="font-mono">TP: {forecast.evaluation_metrics.confusion_matrix[1][1]}</span>
                  </div>
                )}
                {forecast.evaluation_metrics.evaluation_suite && (
                  <div style={{ marginTop: '10px', fontSize: '11px' }}>
                    <div style={{ color: '#38bdf8', fontWeight: 600, marginBottom: '4px' }}>Honest evaluation (5-fold CV)</div>
                    <table className="data-table" style={{ fontSize: '11px' }}>
                      <thead>
                        <tr><th>TEST</th><th>ACCURACY</th><th>F1</th><th>ROC-AUC</th></tr>
                      </thead>
                      <tbody>
                        {Object.entries(forecast.evaluation_metrics.evaluation_suite).map(([name, r]) => (
                          <tr key={name} title={r.description}>
                            <td>{SUITE_LABELS[name] || name}</td>
                            <td className="font-mono">{(r.accuracy_mean * 100).toFixed(1)}%</td>
                            <td className="font-mono">{r.f1_mean.toFixed(2)}</td>
                            <td className="font-mono">{r.roc_auc_mean.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="text-muted" style={{ marginTop: '4px' }}>
                      The label is water level &gt; 4.21 m, so the all-inputs score of 100% is leakage. The served model uses
                      weather only. Next-hour forecasting is near chance because the dataset rows are independent hours.
                    </div>
                  </div>
                )}
                <div className="metrics-footnote" style={{ fontSize: '11px', color: '#94a3b8', marginTop: '8px', lineHeight: '1.4' }}>
                  Trained with scikit-learn on <code>{forecast.data_source}</code> (1,000 gauge readings, STATION_HYDRO_04).
                  <br />
                  <span style={{ color: '#38bdf8' }}>Audit Finding:</span> The 100% classification metric reflects a deterministic water-level boundary (&gt;4.21m = flood risk) in this curated benchmark. 30–60 minute horizon projections are physical hydrological runoff surge scenarios, not multi-step ML predictions.
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-forecast-prompt">
              <Activity size={36} className="text-muted" />
              <p>Adjust inputs and click "Compute AI Flood Forecast" to run real-time inference.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
