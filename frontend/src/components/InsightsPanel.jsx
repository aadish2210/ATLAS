import React, { useEffect, useState } from "react";
import { api } from "../api/client";

function Pct(props) {
  const v = props.value;
  if (v === null || v === undefined || Number.isNaN(v)) return <span>—</span>;
  return <span>{(v * 100).toFixed(1)}%</span>;
}

export default function InsightsPanel() {
  const [backtest, setBacktest] = useState(null);
  const [semantic, setSemantic] = useState(null);
  const [severity, setSeverity] = useState(null);
  const [validation, setValidation] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [b, s, sev, v] = await Promise.all([
          api.backtest(),
          api.semantic(),
          api.severity(),
          api.validation(),
        ]);
        setBacktest(b);
        setSemantic(s);
        setSeverity(sev);
        setValidation(v);
      } catch (e) {
        console.error("insights load failed", e);
      }
    })();
  }, []);

  if (!backtest && !semantic && !severity) {
    return <div className="empty">Loading insights…</div>;
  }

  const hl = backtest?.headline ?? {};
  const sevByCause = severity?.by_cause ?? {};
  const topCauses = Object.entries(sevByCause)
    .sort((a, b) => b[1].n - a[1].n)
    .slice(0, 8);

  return (
    <div className="copilot" style={{ gap: 12 }}>
      <div className="esi-card" style={{ marginBottom: 0 }}>
        <div className="label">Time-machine backtest · cascade discovery</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <div className="esi-value">
            <Pct value={hl.discovery_recall_atlas} />
          </div>
          <div className="muted small">
            ATLAS catches {(hl.discovery_recall_atlas * 100).toFixed(0)}% of
            new afternoon hotspots. A persistence baseline catches only{" "}
            {(hl.discovery_recall_persistence * 100).toFixed(0)}%.
          </div>
        </div>
        <div className="esi-band" style={{ marginTop: 8 }}>
          151 days replayed · cutoff 12:00 IST · micro-averaged.
        </div>
      </div>

      <div className="section-title">
        <span className="dot" />
        Equal-budget ranking @K=10
      </div>
      {backtest?.strategies && (
        <div className="list-item">
          <div className="meta" style={{ fontSize: 11, lineHeight: 1.6 }}>
            <strong>ATLAS</strong> P=
            {backtest.strategies.atlas.k10.precision} R=
            {backtest.strategies.atlas.k10.recall} F1=
            {backtest.strategies.atlas.k10.f1}
            <br />
            <strong>blend (no cascade)</strong> F1=
            {backtest.strategies.blend_no_cascade.k10.f1}
            <br />
            <strong>persistence</strong> F1=
            {backtest.strategies.persistence.k10.f1} ·{" "}
            <strong>prior</strong> F1=
            {backtest.strategies.prior.k10.f1}
          </div>
        </div>
      )}

      <div className="section-title">
        <span className="dot" />
        Multilingual archetypes (Kannada-aware)
      </div>
      {semantic?.archetypes?.slice(0, 5).map((a) => (
        <div className="list-item" key={a.id}>
          <span className="pill">n={a.size}</span>
          <strong>{a.dominant_cause}</strong>
          <div className="meta">
            cause purity {(a.cause_purity * 100).toFixed(0)}% · Kannada{" "}
            {(a.kannada_share * 100).toFixed(0)}% · avg duration{" "}
            {a.avg_duration_min.toFixed(0)} min
          </div>
          {a.examples?.[0] && (
            <div
              className="muted small"
              style={{ marginTop: 4, fontStyle: "italic" }}
            >
              "{a.examples[0]}"
            </div>
          )}
        </div>
      ))}
      {semantic?.kannada_descriptions != null && (
        <div className="muted small">
          {semantic.kannada_descriptions} Kannada descriptions
          ({(semantic.kannada_share_overall * 100).toFixed(1)}% of corpus)
          now contribute to clustering — character n-gram TF-IDF, no
          translation needed.
        </div>
      )}

      <div className="section-title">
        <span className="dot" />
        Evidence base by event cause
      </div>
      <div className="muted small" style={{ marginBottom: 6 }}>
        Severity is derived from outcomes: 0.45·rank(duration) +
        0.25·rank(response) + 0.15·closure + 0.15·rank(cascade).
      </div>
      {topCauses.map(([cause, d]) => (
        <div className="list-item" key={cause}>
          <span
            className={
              "pill " +
              (d.n >= 100 ? "" : d.n >= 20 ? "warn" : "danger")
            }
          >
            n={d.n}
          </span>
          <strong>{cause}</strong>
          <div className="meta">
            sev μ={d.sev_mean} (P10–P90 {d.sev_p10}–{d.sev_p90}) · median
            duration {d.dur_p50} min
          </div>
        </div>
      ))}

      {validation?.metrics && (
        <>
          <div className="section-title">
            <span className="dot" />
            Out-of-time validation
          </div>
          <div className="muted small" style={{ lineHeight: 1.6 }}>
            n={validation.summary?.n_holdout} · MAE{" "}
            {validation.metrics.mae_min}m · 90% interval coverage{" "}
            {(validation.metrics.coverage_90 * 100).toFixed(1)}% · avg width{" "}
            {validation.metrics.avg_interval_width_min} min
          </div>
        </>
      )}
    </div>
  );
}
