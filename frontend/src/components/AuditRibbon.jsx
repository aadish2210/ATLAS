import React from "react";

function n(v, decimals = 1) {
  if (v == null || isNaN(v)) return "—";
  return Number(v).toFixed(decimals);
}

export default function AuditRibbon({ audit }) {
  if (!audit) return null;
  return (
    <div className="audit-ribbon">
      <div className="item">
        <div className="label">Events audited</div>
        <div className="value">{audit.n_events_audited?.toLocaleString()}</div>
      </div>
      <div className="item">
        <div className="label">Avg response (baseline → ATLAS)</div>
        <div className="value">
          {n(audit.baseline?.avg_response_min)} → {n(audit.atlas?.avg_response_min)}
          <span className="delta">−{n(audit.delta_avg_min)} min</span>
        </div>
      </div>
      <div className="item">
        <div className="label">Officer-hours saved</div>
        <div className="value">
          {n(audit.officer_hours_saved)}
          <span className="delta">≈ ₹{n(audit.rupee_impact_lakh, 2)} L</span>
        </div>
      </div>
      <div className="item">
        <div className="label">Equity (Gini ↓ better)</div>
        <div className="value">
          {n(audit.gini_baseline, 2)} → {n(audit.gini_atlas, 2)}
        </div>
      </div>
      <div className="item">
        <div className="label">P90 response (baseline → ATLAS)</div>
        <div className="value">
          {n(audit.baseline?.p90_response_min)} → {n(audit.atlas?.p90_response_min)}
          <span className="delta">−{n(audit.delta_p90_min)} min</span>
        </div>
      </div>
    </div>
  );
}
