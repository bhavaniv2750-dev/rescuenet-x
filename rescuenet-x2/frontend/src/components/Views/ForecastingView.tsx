import React, { useState } from 'react';
import { Activity, Info } from 'lucide-react';
import { api } from '../../api/client';
import type { FloodPredictionResult } from '../../api/types';
import { Button, EmptyState, ErrorState, PageHeader, Panel, ProvenanceBadge, SeverityBadge, StatusBadge } from '../ui';

interface ForecastingViewProps { initialForecast?: FloodPredictionResult | null; /** Technical model details are offered to professional (console) users only. */ showModelDetails?: boolean }

const SUITE_LABELS: Record<string, string> = {
  leaky_baseline_all_features: 'All inputs incl. water level (leakage)',
  early_warning_weather_only: 'Early warning, weather only (served)',
  gauge_noise_0_5m: 'Noisy gauge, sd 0.5 m',
  next_hour_forecast: 'Next-hour forecast',
};
const pct = (x: number) => `${Math.round(x * 100)}%`;
const PRESETS: { label: string; v: [number, number, number, number] }[] = [
  { label: 'Light monsoon', v: [8, 1.8, 65, 30] }, { label: 'Storm surge', v: [42, 4.5, 88, 26] }, { label: 'Severe cloudburst', v: [95, 7.2, 98, 23] },
];

/** Compact trend of the classifier probability (now) and the three heuristic projections. Inline SVG: no chart dependency. */
const ProjectionChart: React.FC<{ now: number; h30: number; h45: number; h60: number }> = ({ now, h30, h45, h60 }) => {
  const pts = [['Now', 0, now], ['+30 min', 30, h30], ['+45 min', 45, h45], ['+60 min', 60, h60]] as const;
  const W = 460, H = 170, L = 40, R = 24, T = 30, B = 30;
  const x = (m: number) => L + ((W - L - R) * m) / 60, y = (v: number) => T + (H - T - B) * (1 - v);
  const alt = pts.map(([l, , v]) => `${l}: ${Math.round(v * 100)}%`).join(', ');
  return (
    <svg className="fc-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Scenario projections of flood probability. ${alt}`}>
      {[0, 0.5, 1].map((g) => <g key={g}><line x1={L} x2={W - R} y1={y(g)} y2={y(g)} className="fc-grid-line" /><text x={L - 6} y={y(g) + 4} textAnchor="end" className="fc-axis">{Math.round(g * 100)}%</text></g>)}
      <polyline className="fc-line" fill="none" strokeDasharray="5 4" points={pts.map(([, m, v]) => `${x(m)},${y(v)}`).join(' ')} />
      {pts.map(([l, m, v], i) => (
        <g key={l}><circle cx={x(m)} cy={y(v)} r={i === 0 ? 5 : 4} className={i === 0 ? 'fc-dot-now' : 'fc-dot'} />
          <text x={x(m)} y={y(v) - 11} textAnchor={i === 3 ? 'end' : i === 0 ? 'start' : 'middle'} className="fc-val">{Math.round(v * 100)}%</text>
          <text x={x(m)} y={H - 8} textAnchor={i === 3 ? 'end' : i === 0 ? 'start' : 'middle'} className="fc-axis">{l}</text></g>
      ))}
    </svg>
  );
};

const Slider: React.FC<{ id: string; label: string; unit: string; value: number; min: number; max: number; step: number; onChange: (n: number) => void; hints: string }> = ({ id, label, unit, value, min, max, step, onChange, hints }) => (
  <div className="fc-slider">
    <div className="fc-slider-top">
      <label htmlFor={id}>{label}</label>
      <span className="fc-value">{value.toFixed(step < 1 ? 1 : 0)} {unit}</span>
    </div>
    <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(parseFloat(e.target.value))} className="range-slider" aria-describedby={`${id}-hint`} />
    <span id={`${id}-hint`} className="rn-field-hint">{hints}</span>
  </div>
);

export const ForecastingView: React.FC<ForecastingViewProps> = ({ initialForecast, showModelDetails = false }) => {
  const [rainfall, setRainfall] = useState(38);
  const [waterLevel, setWaterLevel] = useState(4.2);
  const [humidity, setHumidity] = useState(85);
  const [temperature, setTemperature] = useState(27);
  const [forecast, setForecast] = useState<FloodPredictionResult | null>(initialForecast || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true); setError(null);
    try { setForecast(await api.predictFlood({ rainfall_mm: rainfall, water_level_m: waterLevel, humidity_pct: humidity, temperature_c: temperature })); }
    catch (err) { setError(err instanceof Error ? err.message : 'The forecast could not be computed.'); }
    finally { setLoading(false); }
  };
  const apply = (v: [number, number, number, number]) => { setRainfall(v[0]); setWaterLevel(v[1]); setHumidity(v[2]); setTemperature(v[3]); };
  const m = forecast?.evaluation_metrics;

  return (
    <div className="forecasting-container">
      <PageHeader title="Flood risk forecasting"
        description="Scenario-based flood risk estimate from the inputs you set. It is not a live forecast."
        meta={<><ProvenanceBadge kind="SIMULATED" /><span className="rn-field-hint">scenario inputs, not sensor readings</span><ProvenanceBadge kind="HISTORICAL" /><span className="rn-field-hint">trained on a historical dataset</span></>} />

      <div className="fc-grid">
        <Panel title="Scenario inputs" actions={<span className="rn-field-hint">Presets:</span>}>
          <form className="fc-form" onSubmit={(e) => { e.preventDefault(); run(); }}>
            <div className="fc-presets">{PRESETS.map((p) => <Button key={p.label} size="sm" onClick={() => apply(p.v)}>{p.label}</Button>)}</div>
            <Slider id="fc-rain" label="Rainfall intensity" unit="mm/hr" value={rainfall} min={0} max={120} step={0.5} onChange={setRainfall} hints="0 dry, about 35 heavy, 120 extreme cloudburst" />
            <Slider id="fc-level" label="Water level" unit="m" value={waterLevel} min={0} max={10} step={0.1} onChange={setWaterLevel} hints="Scenario value. It is not a classifier input: it sets the gauge-rule floor on the risk level (2.5, 3.8 and 5.5 m)." />
            <Slider id="fc-hum" label="Relative humidity" unit="%" value={humidity} min={20} max={100} step={1} onChange={setHumidity} hints="20 dry air to 100 saturated" />
            <Slider id="fc-temp" label="Air temperature" unit="°C" value={temperature} min={10} max={45} step={0.5} onChange={setTemperature} hints="10 cold to 45 heatwave" />
            <Button type="submit" variant="primary" block loading={loading}>Compute flood risk</Button>
          </form>
        </Panel>

        <Panel title="Result">
          {error ? <ErrorState message={error} onRetry={run} /> : !forecast ? (
            <EmptyState title="No scenario computed yet" icon={<Activity size={22} />}>Adjust the inputs and compute to see the classification, probability and model details.</EmptyState>
          ) : (
            <div className="fc-result">
              {forecast.is_example_scenario && <StatusBadge tone="warn">Example scenario, not current conditions</StatusBadge>}
              <div className="fc-banner">
                <div>
                  <span className="fc-eyebrow">Current risk classification</span>
                  <div className="fc-risk"><SeverityBadge severity={forecast.risk_level} /></div>
                  <p className="fc-advice">{forecast.advisory}</p>
                </div>
                <div className="fc-prob" aria-label={`Model probability ${pct(forecast.probability)}`}>
                  <strong>{pct(forecast.probability)}</strong>
                  <span>model probability</span>
                </div>
              </div>

              <section aria-labelledby="fc-h-horizon">
                <h3 id="fc-h-horizon">Next-hour scenario projections <ProvenanceBadge kind="SIMULATED" /></h3>
                <ProjectionChart now={forecast.probability} h30={forecast.horizon_30m} h45={forecast.horizon_45m} h60={forecast.horizon_60m} />
                <p className="rn-field-hint">Heuristic scenario projections from a fixed runoff formula applied to your rainfall input. They are not independently validated time-series forecasts and do not use current sensor data.</p>
              </section>

              <section aria-labelledby="fc-h-why">
                <h3 id="fc-h-why">Contributing factors</h3>
                <div className="rn-table-wrap"><table className="rn-table"><caption className="rn-sr">Contributing factors</caption>
                  <thead><tr><th scope="col">Factor</th><th scope="col">Effect</th><th scope="col">Importance</th></tr></thead>
                  <tbody>{forecast.contributing_factors.map((f) => <tr key={f.factor}><td>{f.factor}</td><td>{f.impact}</td><td className="auth-mono">{(f.weight * 100).toFixed(1)}%</td></tr>)}</tbody></table></div>
              </section>

              {showModelDetails && m && (
                <details className="rn-about-data fc-model-details">
                  <summary>Model details (technical)</summary>
                  <div className="fc-details-body">
                    <dl className="fc-dl">
                      <dt>Algorithm</dt><dd>{m.model_architecture}</dd>
                      <dt>Model name</dt><dd>{forecast.model_name}</dd>
                      <dt>Classifier inputs</dt><dd className="auth-mono">{m.model_inputs?.join(', ') ?? 'weather inputs'}</dd>
                      <dt>Water level</dt><dd>Not a classifier input. It is applied as a separate gauge rule that can raise the risk class (at 2.5, 3.8 and 5.5 m) and is shown as a contributing factor with no model weight. It does not change the +30/+45/+60 projections, which use only the classifier probability and the rainfall input.</dd>
                      <dt>Dataset</dt><dd><code>{forecast.data_source.split(' ')[0]}</code>, supplied with the project; its collection method is not independently verified here.</dd>
                      <dt>Partition</dt><dd>{m.training_samples} training / {m.test_samples} test records (stratified 80/20 split of the same dataset)</dd>
                      {m.evaluation_version !== undefined && <><dt>Evaluation version</dt><dd>{m.evaluation_version}</dd></>}
                    </dl>
                    <h4>Evaluation (same historical dataset only)</h4>
                    <dl className="fc-dl fc-metrics">
                      <dt>Hold-out accuracy (20% test split)</dt><dd>{(m.accuracy * 100).toFixed(1)}%</dd>
                      {m.cv_5fold_accuracy_mean !== undefined && (<><dt>5-fold cross-validation accuracy</dt><dd>{(m.cv_5fold_accuracy_mean * 100).toFixed(1)}% (±{((m.cv_5fold_accuracy_std ?? 0) * 100).toFixed(1)}); this is the figure in the confidence note: {forecast.confidence_level}</dd></>)}
                      <dt>Precision / recall</dt><dd>{(m.precision * 100).toFixed(1)}% / {(m.recall * 100).toFixed(1)}%</dd>
                      <dt>ROC-AUC</dt><dd>{m.roc_auc.toFixed(3)}</dd>
                      {m.confusion_matrix && (<><dt>Confusion matrix</dt><dd className="auth-mono">TN {m.confusion_matrix[0][0]} · FP {m.confusion_matrix[0][1]} · FN {m.confusion_matrix[1][0]} · TP {m.confusion_matrix[1][1]}</dd></>)}
                    </dl>
                    {m.evaluation_suite && (
                      <div className="rn-table-wrap"><table className="rn-table"><caption className="rn-sr">Evaluation suite</caption>
                        <thead><tr><th scope="col">Test</th><th scope="col">Accuracy</th><th scope="col">F1</th><th scope="col">ROC-AUC</th></tr></thead>
                        <tbody>{Object.entries(m.evaluation_suite).map(([name, r]) => (
                          <tr key={name} title={r.description}><td>{SUITE_LABELS[name] || name}</td><td className="auth-mono">{(r.accuracy_mean * 100).toFixed(1)}%</td><td className="auth-mono">{r.f1_mean.toFixed(2)}</td><td className="auth-mono">{r.roc_auc_mean.toFixed(3)}</td></tr>
                        ))}</tbody></table></div>
                    )}
                    <div className="fc-limits" role="note"><Info size={16} aria-hidden="true" />
                      <p>Cross-validation and hold-out figures come from the same historical dataset, so they are not independent evidence of performance on future events. The label is "water level above 4.21 m", so any score that uses the water level is near-perfect because of leakage; the served model uses weather inputs only. Next-hour forecasting from this dataset is close to chance.</p>
                    </div>
                  </div>
                </details>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
};
