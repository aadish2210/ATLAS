import React from "react";
import { useCounter } from "../hooks/useAnimation";

function Kpi({ label, value, unit, accent, warn, format = "int" }) {
  const animated = useCounter(value, 1000);
  const display =
    format === "int"
      ? Math.round(animated).toLocaleString()
      : animated.toFixed(1);
  return (
    <div className={"kpi" + (accent ? " accent" : "") + (warn ? " warn" : "")}>
      <div className="label">{label}</div>
      <div className="value">
        {display}
        {unit && <span className="unit">{unit}</span>}
      </div>
    </div>
  );
}

export default function KpiBar({ city, audit, hour }) {
  const events = city?.city?.events ?? 0;
  const corridors = city?.n_corridors ?? 0;
  const officerHrs = audit?.officer_hours_saved ?? 0;
  const deltaMin = audit?.delta_avg_min ?? 0;

  return (
    <>
      <Kpi label="Events analyzed" value={events} accent />
      <Kpi label="Corridors profiled" value={corridors} />
      <Kpi
        label="Officer-hours saved"
        value={officerHrs}
        unit="hrs"
        format="float"
        accent
      />
      <Kpi
        label="Avg response delta"
        value={deltaMin}
        unit="min"
        format="float"
        warn
      />
    </>
  );
}
