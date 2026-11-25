import React, { useState } from 'react';
import { Activity, Info } from 'lucide-react';
import { api } from '../../api/client';
import type { FloodPredictionResult } from '../../api/types';
import { Button, EmptyState, ErrorState, PageHeader, Panel, ProvenanceBadge, SeverityBadge, StatusBadge } from '../ui';

interface ForecastingViewProps { initialForecast?: FloodPredictionResult | null }

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

export const ForecastingView: React.FC<ForecastingViewProps> = ({ initialForecast }) => {
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
        description="A scenario tool: a classifier estimates flood risk from the inputs you set. It is not a live forecast and does not read current sensors."
        meta={<><ProvenanceBadge kind="HISTORICAL" /><span className="rn-field-hint">Trained on 1,000 records supplied with the project; their collection method is not independently verified here</span><ProvenanceBadge kind="SIMULATED" /><span className="rn-field-hint">Inputs are scenario values you choose</span></>} />

      <div className="fc-grid">
        <Panel title="Scenario inputs" actions={<span className="rn-field-hint">Presets:</span>}>
          <form className="fc-form" onSubmit={(e) => { e.preventDefault(); run(); }}>
            <div className="fc-presets">{PRESETS.map((p) => <Button key={p.label} size="sm" onClick={() => apply(p.v)}>{p.label}</Button>)}</div>
            <Slider id="fc-rain" label="Rainfall intensity" unit="mm/hr" value={rainfall} min={0} max={120} step={0.5} onChange={setRainfall} hints="0 dry, about 35 heavy, 120 extreme cloudburst" />
            <Slider id="fc-level" label="Water level" unit="m" value={waterLevel} min={0} max={10} step={0.1} onChange={setWaterLevel} hints="Training labels flood risk above 4.21 m" />
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
                <h3 id="fc-h-horizon">Scenario projections <ProvenanceBadge kind="SIMULATED" /></h3>
                <p className="rn-field-hint">+30, +45 and +60 minute values come from a fixed heuristic runoff formula applied to your inputs. They are <strong>not</strong> independently validated forecasts and are not predictions of the trained model.</p>
                {([['+30 minutes', forecast.horizon_30m], ['+45 minutes', forecast.horizon_45m], ['+60 minutes', forecast.horizon_60m]] as const).map(([label, v]) => (
                  <div key={label} className="fc-bar">
                    <div className="fc-bar-top"><span>{label}</span><span className="auth-mono">{pct(v)}</span></div>
                    <div className="progress-track" role="img" aria-label={`${label}: ${pct(v)}`}><div className="progress-fill" style={{ width: pct(v), background: v > 0.7 ? 'var(--sev-critical)' : v > 0.4 ? 'var(--sev-high)' : 'var(--sev-moderate)' }} /></div>
                  </div>
                ))}
              </section>

              <section aria-labelledby="fc-h-model">
                <h3 id="fc-h-model">Model information</h3>
                <dl className="fc-dl">
                  <dt>Model</dt><dd>{forecast.model_name} ({m?.model_architecture})</dd>
                  <dt>Confidence note</dt><dd>{forecast.confidence_level}</dd>
                  <dt>Training data</dt><dd><code>{forecast.data_source.split(' ')[0]}</code> · {m?.training_samples} training / {m?.test_samples} test records (supplied with the project; origin not independently verified)</dd>
                  <dt>Inputs used</dt><dd>{m?.model_inputs?.join(', ') ?? 'weather inputs'}</dd>
                </dl>
              </section>

              <section aria-labelledby="fc-h-why">
                <h3 id="fc-h-why">Contributing factors</h3>
                <div className="rn-table-wrap"><table className="rn-table"><caption className="rn-sr">Contributing factors</caption>
                  <thead><tr><th scope="col">Factor</th><th scope="col">Effect</th><th scope="col">Importance</th></tr></thead>
                  <tbody>{forecast.contributing_factors.map((f) => <tr key={f.factor}><td>{f.factor}</td><td>{f.impact}</td><td className="auth-mono">{(f.weight * 100).toFixed(1)}%</td></tr>)}</tbody></table></div>
              </section>

              {m && (
                <section aria-labelledby="fc-h-val">
                  <h3 id="fc-h-val">Validation and limitations</h3>
                  <p className="rn-field-hint">Measured on a held-out part of the same historical dataset. These figures describe this dataset only, not performance on real future events.</p>
                  <dl className="fc-dl fc-metrics">
                    <dt>Hold-out accuracy</dt><dd>{(m.accuracy * 100).toFixed(1)}%</dd>
                    {m.cv_5fold_accuracy_mean !== undefined && (<><dt>5-fold cross-validation</dt><dd>{(m.cv_5fold_accuracy_mean * 100).toFixed(1)}% (±{((m.cv_5fold_accuracy_std ?? 0) * 100).toFixed(1)})</dd></>)}
                    <dt>Precision / recall</dt><dd>{(m.precision * 100).toFixed(1)}% / {(m.recall * 100).toFixed(1)}%</dd>
                    <dt>ROC-AUC</dt><dd>{m.roc_auc.toFixed(3)}</dd>
                    {m.confusion_matrix && (<><dt>Confusion matrix</dt><dd className="auth-mono">TN {m.confusion_matrix[0][0]} · FP {m.confusion_matrix[0][1]} · FN {m.confusion_matrix[1][0]} · TP {m.confusion_matrix[1][1]}</dd></>)}
                  </dl>
                  {m.evaluation_suite && (
                    <div className="rn-table-wrap"><table className="rn-table"><caption className="rn-sr">Evaluation suite</caption>
                      <thead><tr><th scope="col">Test</th><th scope="col">Accuracy</th><th scope="col">F1</th><th scope="col">ROC-AUC</th></tr></thead>
                      <tbody>{Object.entries(m.evaluation_suite).map(([name, r]) => (
                        <tr key={name} title={r.description}><td>{SUITE_LABELS[name] || name}</td><td className="auth-mono">{(r.accuracy_mean * 100).toFixed(1)}%</td><td className="auth-mono">{r.f1_mean.toFixed(2)}</td><td className="auth-mono">{r.roc_auc_mean.toFixed(2)}</td></tr>))}</tbody></table></div>
                  )}
                  <div className="fc-limits" role="note"><Info size={16} aria-hidden="true" />
                    <p>The label is “water level above 4.21 m”, so any score that uses the water level is near-perfect because of leakage. The served model uses weather inputs only. Next-hour forecasting is close to chance because the dataset rows are independent hours. Treat the output as a demonstration of the method, not an operational warning.</p></div>
                </section>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
};
