import React, { useEffect, useRef } from "react";
import * as d3 from "d3";

/**
 * Polar 24h clock with anomaly day spikes.
 * Inputs:
 *   breathing: number[24] in [0..1]
 *   anomalyDays: [{date, count, z}]
 *   predictability: number 0..1
 *   label: string
 */
export default function FingerprintClock({
  breathing,
  anomalyDays = [],
  predictability = 0,
  label = "City",
}) {
  const ref = useRef(null);
  useEffect(() => {
    if (!breathing || !ref.current) return;
    const size = 260;
    const r0 = 30;
    const r1 = 110;

    const svg = d3
      .select(ref.current)
      .attr("viewBox", `0 0 ${size} ${size}`)
      .attr("preserveAspectRatio", "xMidYMid meet");
    svg.selectAll("*").remove();

    const g = svg.append("g").attr("transform", `translate(${size / 2}, ${size / 2})`);

    // halo
    g.append("circle")
      .attr("r", r1 + 12)
      .attr("fill", "rgba(56, 189, 248, 0.04)")
      .attr("stroke", "rgba(56, 189, 248, 0.18)")
      .attr("stroke-dasharray", "2 4");
    g.append("circle")
      .attr("r", r0)
      .attr("fill", "rgba(56, 189, 248, 0.08)")
      .attr("stroke", "rgba(56, 189, 248, 0.2)");

    // 24 wedges
    const arc = d3
      .arc()
      .innerRadius(r0 + 2)
      .startAngle((_, i) => (i / 24) * Math.PI * 2)
      .endAngle((_, i) => ((i + 1) / 24) * Math.PI * 2)
      .padAngle(0.015)
      .cornerRadius(2);

    const colors = d3.interpolateRgb("#1e3a8a", "#f472b6");

    g.selectAll("path.wedge")
      .data(breathing)
      .join("path")
      .attr("class", "wedge")
      .attr("d", (d, i) =>
        arc({ outerRadius: r0 + 4 + d * (r1 - r0 - 4) }, i)
      )
      .attr("fill", (d) => colors(d))
      .attr("opacity", 0.85)
      .attr("stroke", "rgba(56, 189, 248, 0.4)")
      .attr("stroke-width", 0.6);

    // hour ticks
    g.selectAll("text.hour")
      .data([0, 6, 12, 18])
      .join("text")
      .attr("class", "hour")
      .attr("x", (d) => Math.sin((d / 24) * Math.PI * 2) * (r1 + 14))
      .attr("y", (d) => -Math.cos((d / 24) * Math.PI * 2) * (r1 + 14))
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle")
      .attr("fill", "#5d7896")
      .attr("font-size", 9)
      .text((d) => `${d.toString().padStart(2, "0")}h`);

    // anomaly markers (dots placed by date hash on outer ring)
    g.selectAll("circle.anom")
      .data(anomalyDays.slice(0, 12))
      .join("circle")
      .attr("class", "anom")
      .attr("cx", (d, i) => Math.sin((i / 12) * Math.PI * 2) * (r1 + 6))
      .attr("cy", (d, i) => -Math.cos((i / 12) * Math.PI * 2) * (r1 + 6))
      .attr("r", (d) => 2 + Math.min(6, d.z))
      .attr("fill", "#f87171")
      .attr("stroke", "#fff")
      .attr("stroke-width", 0.5)
      .attr("opacity", 0.85)
      .append("title")
      .text((d) => `${d.date} · ${d.count} events · z=${d.z}`);

    // center label — feature the genuine finding (anomaly days), not a raw %
    g.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", -6)
      .attr("fill", "#38bdf8")
      .attr("font-size", 24)
      .attr("font-weight", 800)
      .text(`${anomalyDays.length}`);
    g.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", 10)
      .attr("fill", "#e6f1ff")
      .attr("font-size", 10)
      .attr("font-weight", 600)
      .text("anomaly days");
    g.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", 22)
      .attr("fill", "#5d7896")
      .attr("font-size", 8)
      .text("found · no calendar");
  }, [breathing, anomalyDays, predictability]);

  return (
    <div className="fingerprint-clock">
      <svg ref={ref} />
      <div className="meta">
        <strong>{label}</strong> · 24-h rhythm · red dots = unusual surge days
        (festivals/rallies) found with no calendar
      </div>
    </div>
  );
}
