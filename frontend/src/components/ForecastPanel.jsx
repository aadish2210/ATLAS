import React from "react";

function fmtPct(n) {
  return `${(n * 100).toFixed(0)}%`;
}

export default function ForecastPanel({ simulation, evidenceCount = 0 }) {
  if (!simulation) {
    return (
      <div className="side-panel right-panel">
        <div className="head">
          <h3>Forecast & response plan</h3>
        </div>
        <div className="body">
          <div className="empty">
            <div className="icon">◈</div>
            Drop an event on the map and ATLAS will predict ESI, secondary
            cascades, and the optimal officer deployment plan with
            barricading and diversion guidance.
          </div>
        </div>
      </div>
    );
  }

  const { esi, cascade, deployment, diversions, barricades, summary, context, evidence, optimization } =
    simulation;
  const drivers = esi.drivers || {};
  const bandWidth = Math.max(0, (esi.high ?? 0) - (esi.low ?? 0));
  const uncertainty = Math.min(1, bandWidth / 10);
  const firstHop = cascade.filter((c) => (c.hop ?? 1) === 1);
  const signal =
    firstHop.length > 0
      ? firstHop.reduce((acc, c) => acc + c.prob * (1 - Math.min(1, c.p_value || 1)), 0) /
        firstHop.length
      : 0.25;
  const confidence = Math.max(0, Math.min(1, 0.2 + 0.5 * (1 - uncertainty) + 0.3 * signal));
  const confidenceLabel = confidence >= 0.75 ? "High" : confidence >= 0.5 ? "Medium" : "Low";

  return (
    <div className="side-panel right-panel">
      <div className="head">
        <h3>Forecast & response plan</h3>
        <span className="live-pill">live</span>
      </div>
      <div className="body">
        <div className="esi-card">
          <div className="label">Event Severity Index</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <div className="esi-value">{esi.esi.toFixed(1)}</div>
            <div className="muted small">/ 10</div>
          </div>
          <div className="esi-band">
            90% interval [{esi.low.toFixed(1)} — {esi.high.toFixed(1)}] ·
            Predicted duration {esi.duration_min.toFixed(0)} min
            {esi.duration_low != null && (
              <span className="muted">
                {" "}
                ({esi.duration_low.toFixed(0)}–{esi.duration_high.toFixed(0)})
              </span>
            )}
          </div>
          <div className="driver-list">
            <div className="driver">
              <div className="k">Closure</div>
              <div className="v">{drivers.closure ? "Yes" : "No"}</div>
            </div>
            <div className="driver">
              <div className="k">Cascade</div>
              <div className="v">{fmtPct(drivers.cascade_norm ?? 0)}</div>
            </div>
            <div className="driver">
              <div className="k">Corridor</div>
              <div className="v">{fmtPct(drivers.corridor_norm ?? 0)}</div>
            </div>
            <div className="driver">
              <div className="k">Size</div>
              <div className="v">{fmtPct(drivers.size_w ?? 0)}</div>
            </div>
            <div className="driver">
              <div className="k">Duration</div>
              <div className="v">{fmtPct(drivers.duration_norm ?? 0)}</div>
            </div>
            <div className="driver">
              <div className="k">Night</div>
              <div className="v">×{(drivers.night_factor ?? 1).toFixed(2)}</div>
            </div>
          </div>
        </div>

        <div className="section-title">
          <span className="dot" />
          How reliable is this forecast?
        </div>
        {evidence && (
          <div className="list-item" style={{ marginBottom: 8 }}>
            <span
              className={
                "pill " +
                (evidence.tier === "data_driven"
                  ? ""
                  : evidence.tier === "limited"
                  ? "warn"
                  : "danger")
              }
            >
              {evidence.tier === "data_driven"
                ? "data-driven"
                : evidence.tier === "limited"
                ? "limited evidence"
                : "insufficient evidence"}
            </span>
            <strong>{evidence.cause}</strong>
            <div className="meta">{evidence.message}</div>
            {evidence.sev_mean != null && (
              <div className="meta">
                historical sev μ={evidence.sev_mean} (P10–P90{" "}
                {evidence.sev_p10}–{evidence.sev_p90})
              </div>
            )}
          </div>
        )}
        <div className="trust-card">
          <div className="trust-header">
            <strong>{confidenceLabel} confidence</strong>
            <span>{Math.round(confidence * 100)}%</span>
          </div>
          <div className="trust-meter">
            <div className="trust-fill" style={{ width: `${Math.round(confidence * 100)}%` }} />
          </div>
          <div className="muted small" style={{ marginTop: 8, lineHeight: 1.6 }}>
            Confidence blends uncertainty band width and cascade statistical strength. Narrower ESI bands and low p-values
            increase trust. Historical evidence pool: {evidenceCount || "unknown"} events. This is decision support, not certainty.
          </div>
        </div>

        <div className="section-title">
          <span className="dot" />
          Cascading secondaries · {cascade.length}
        </div>
        {cascade.length === 0 && (
          <div className="muted small">No significant downstream cascades.</div>
        )}
        {cascade.slice(0, 6).map((c, i) => (
          <div className="list-item" key={i}>
            <span className="pill">P {(c.prob * 100).toFixed(0)}%</span>
            <strong>{c.to}</strong>
            <div className="meta">
              from {c.from} · ETA ~{c.delay_min.toFixed(0)} min · lift ×
              {c.lift.toFixed(1)} · p={c.p_value.toFixed(3)}
              {c.hop === 2 ? " · 2nd hop" : ""}
            </div>
          </div>
        ))}

        <div className="section-title">
          <span className="dot" />
          Manpower deployment · {summary.n_officers_recommended} officers
        </div>
        {optimization && optimization.n_demands > 1 && (
          <>
            <div className="section-title">
              <span className="dot" />
              Optimal allocation · Hungarian assignment
            </div>
            <div className="trust-card" style={{ marginBottom: 8 }}>
              <div className="trust-header">
                <strong>
                  {optimization.optimal_avg_eta_min} min avg ETA
                </strong>
                <span>{optimization.pct_faster}% faster</span>
              </div>
              <div className="muted small" style={{ marginTop: 6 }}>
                vs greedy {optimization.greedy_avg_eta_min} min · {optimization.n_demands} demands × {optimization.n_stations} stations · solved with {optimization.method.split("(")[0].trim()}.
              </div>
            </div>
          </>
        )}
        {deployment.map((d, i) => (
          <div className="list-item" key={i}>
            <span className={"pill " + (d.kind === "primary" ? "" : "warn")}>
              {d.kind}
            </span>
            <strong>{d.station}</strong> → {d.officers} officer
            {d.officers > 1 ? "s" : ""}
            <div className="meta">
              ETA {d.eta_min.toFixed(0)} min · {d.distance_km.toFixed(1)} km ·
              load {fmtPct(d.load_factor)}
            </div>
          </div>
        ))}

        {barricades.length > 0 && (
          <>
            <div className="section-title">
              <span className="dot" />
              Barricades · {barricades.length}
            </div>
            <div className="muted small">
              Pre-positioned at predicted closure perimeter.
            </div>
          </>
        )}

        {diversions.length > 0 && (
          <>
            <div className="section-title">
              <span className="dot" />
              Diversions · {diversions.length}
            </div>
            {diversions.map((d, i) => (
              <div className="list-item" key={i}>
                <span className="pill">{d.distance_km.toFixed(1)} km</span>
                <strong>{d.corridor}</strong>
                <div className="meta">
                  predicted residual load {d.predicted_residual_pct}%
                </div>
              </div>
            ))}
          </>
        )}

        <div className="divider" />
        <div className="muted small">
          Context: corridor <strong>{context.corridor || "—"}</strong> · zone{" "}
          <strong>{context.zone || "—"}</strong> · nearest station{" "}
          <strong>{context.nearest_station || "—"}</strong>.
        </div>
      </div>
    </div>
  );
}
