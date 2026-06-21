import { GeoJsonLayer, LineLayer, ScatterplotLayer, ArcLayer, TextLayer } from "@deck.gl/layers";
import { esiColor, probColor, withAlpha } from "../utils/colors";

/** Corridor breathing layer — colors corridors by ESI at the current hour. */
export function corridorLayer({ corridors, corridorState, hour }) {
  if (!corridors || !corridors.features) return null;
  return new GeoJsonLayer({
    id: "corridors",
    data: corridors,
    stroked: true,
    filled: false,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 4,
    lineWidthMaxPixels: 14,
    getLineWidth: (f) => 4 + (f.properties.criticality || 0) * 7,
    getLineColor: (f) => {
      const name = f.properties.name;
      const st = corridorState?.[name];
      const esi = st?.esi_by_hour?.[hour] ?? 4;
      return withAlpha(esiColor(esi), 0.88);
    },
    pickable: true,
    updateTriggers: {
      getLineColor: [hour, corridorState],
    },
  });
}

/** Soft glow underlay to make corridor colors visible on any basemap. */
export function corridorGlowLayer({ corridors, corridorState, hour }) {
  if (!corridors || !corridors.features) return null;
  return new GeoJsonLayer({
    id: "corridors-glow",
    data: corridors,
    stroked: true,
    filled: false,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 8,
    lineWidthMaxPixels: 18,
    getLineWidth: (f) => 8 + (f.properties.criticality || 0) * 6,
    getLineColor: (f) => {
      const name = f.properties.name;
      const st = corridorState?.[name];
      const esi = st?.esi_by_hour?.[hour] ?? 4;
      return withAlpha(esiColor(esi), 0.22);
    },
    pickable: false,
    updateTriggers: {
      getLineColor: [hour, corridorState],
    },
  });
}

/** Stations as glowing dots. */
export function stationLayer({ stations, hour }) {
  if (!stations) return null;
  return new ScatterplotLayer({
    id: "stations",
    data: stations,
    getPosition: (d) => [d.lng, d.lat],
    getFillColor: (d) => {
      const load = d.hourly_load?.[hour] ?? 0.5;
      const rgb = esiColor(load * 10);
      return withAlpha(rgb, 0.85);
    },
    getRadius: (d) => 80 + Math.sqrt(d.events) * 12,
    radiusUnits: "meters",
    radiusMinPixels: 4,
    radiusMaxPixels: 24,
    stroked: true,
    getLineColor: [56, 189, 248, 200],
    lineWidthMinPixels: 1,
    pickable: true,
    updateTriggers: { getFillColor: [hour] },
  });
}

/** Animated cascade visualization — labeled impact zones with rank, probability, and ETA.
 *  Each predicted secondary appears as a numbered, color-coded zone so users can
 *  immediately read "order of cascade", "how likely", and "how soon". */
export function cascadeLayers({ seed, ripple, t }) {
  if (!seed) return [];
  const layers = [];

  // Single subtle pulse around the seed (one ring, not three) — much lighter on GPU.
  layers.push(
    new ScatterplotLayer({
      id: "cascade-seed-pulse",
      data: [{ r: 400 + 600 * t }],
      getPosition: () => [seed.lng, seed.lat],
      getRadius: (d) => d.r,
      radiusUnits: "meters",
      stroked: true,
      filled: false,
      getLineColor: withAlpha([244, 114, 182], Math.max(0.05, 0.6 - 0.5 * t)),
      lineWidthMinPixels: 2,
      updateTriggers: { getRadius: [t], getLineColor: [t] },
    })
  );

  // Seed pin (your event)
  layers.push(
    new ScatterplotLayer({
      id: "cascade-seed",
      data: [seed],
      getPosition: (d) => [d.lng, d.lat],
      getFillColor: [244, 114, 182, 230],
      getRadius: 180,
      radiusMinPixels: 8,
      stroked: true,
      getLineColor: [255, 255, 255, 220],
      lineWidthMinPixels: 2,
    })
  );

  if (!ripple?.length) return layers;

  // Rank cascades by probability and keep top 6 to avoid clutter.
  const ranked = [...ripple]
    .sort((a, b) => b.prob - a.prob)
    .slice(0, 6)
    .map((r, i) => ({ ...r, rank: i + 1 }));

  // Impact zone — color = severity (probability), size = stable, no flicker.
  layers.push(
    new ScatterplotLayer({
      id: "cascade-zones",
      data: ranked,
      getPosition: (d) => [d.to_lng, d.to_lat],
      getRadius: 500,
      radiusUnits: "meters",
      radiusMinPixels: 14,
      radiusMaxPixels: 36,
      stroked: true,
      filled: true,
      getFillColor: (d) => withAlpha(probColor(d.prob), 0.32),
      getLineColor: (d) => withAlpha(probColor(d.prob), 0.95),
      lineWidthMinPixels: 2,
      pickable: true,
    })
  );

  // Connecting line from event -> impact zone (first hop only).
  layers.push(
    new LineLayer({
      id: "cascade-lines",
      data: ranked.filter((r) => (r.hop ?? 1) === 1),
      getSourcePosition: () => [seed.lng, seed.lat],
      getTargetPosition: (d) => [d.to_lng, d.to_lat],
      getColor: (d) => withAlpha(probColor(d.prob), 0.6),
      getWidth: (d) => 1 + d.prob * 3,
      widthUnits: "pixels",
    })
  );

  // Rank number on each impact zone — makes order of cascade obvious.
  layers.push(
    new TextLayer({
      id: "cascade-rank",
      data: ranked,
      getPosition: (d) => [d.to_lng, d.to_lat],
      getText: (d) => String(d.rank),
      getSize: 14,
      sizeUnits: "pixels",
      getColor: [255, 255, 255, 245],
      getTextAnchor: "middle",
      getAlignmentBaseline: "center",
      fontWeight: 700,
      billboard: true,
      pickable: false,
    })
  );

  // Human-readable label above each zone: "68% · ~12 min"
  layers.push(
    new TextLayer({
      id: "cascade-label",
      data: ranked,
      getPosition: (d) => [d.to_lng, d.to_lat],
      getText: (d) =>
        `${Math.round(d.prob * 100)}% · ~${Math.round(d.delay_min)} min`,
      getSize: 11,
      sizeUnits: "pixels",
      getColor: [15, 23, 42, 235],
      background: true,
      getBackgroundColor: [255, 255, 255, 235],
      backgroundPadding: [4, 2],
      getTextAnchor: "middle",
      getAlignmentBaseline: "bottom",
      getPixelOffset: [0, -18],
      billboard: true,
      pickable: false,
    })
  );

  return layers;
}

/** User-selected event pin with a single soft pulse ring (lightweight). */
export function eventPinLayers({ pin, t }) {
  if (!pin) return [];

  const ring = new ScatterplotLayer({
    id: "event-pin-rings",
    data: [{ r: 180 + 220 * t }],
    getPosition: () => [pin.lng, pin.lat],
    getRadius: (d) => d.r,
    radiusUnits: "meters",
    stroked: true,
    filled: false,
    getLineColor: withAlpha([244, 114, 182], Math.max(0.05, 0.6 - 0.5 * t)),
    lineWidthMinPixels: 2,
    updateTriggers: { getRadius: [t], getLineColor: [t] },
  });

  const core = new ScatterplotLayer({
    id: "event-pin-core",
    data: [pin],
    getPosition: (d) => [d.lng, d.lat],
    getFillColor: [244, 114, 182, 230],
    getRadius: 120,
    radiusUnits: "meters",
    radiusMinPixels: 8,
    stroked: true,
    getLineColor: [255, 255, 255, 220],
    lineWidthMinPixels: 2,
    pickable: true,
  });

  return [ring, core];
}

/** Replay layer: incidents that have fired so far, plus active cascade edges. */
export function replayLayers({ timeline, minute }) {
  if (!timeline) return [];
  const events = (timeline.events || []).filter((e) => e.minute <= minute);
  const recent = events.filter((e) => minute - e.minute <= 60);

  const layers = [];
  if (events.length) {
    layers.push(
      new ScatterplotLayer({
        id: "replay-events",
        data: events,
        getPosition: (d) => [d.lng, d.lat],
        getRadius: 140,
        radiusUnits: "meters",
        radiusMinPixels: 4,
        getFillColor: (d) =>
          withAlpha(
            d.cause === "vehicle_breakdown"
              ? [56, 189, 248]
              : d.cause === "water_logging"
              ? [34, 211, 238]
              : d.cause === "tree_fall"
              ? [251, 191, 36]
              : [244, 114, 182],
            Math.max(0.25, 1 - (minute - d.minute) / 360)
          ),
        stroked: true,
        getLineColor: [255, 255, 255, 160],
        lineWidthMinPixels: 1,
        pickable: true,
      })
    );
    if (recent.length) {
      layers.push(
        new ScatterplotLayer({
          id: "replay-recent-pulse",
          data: recent,
          getPosition: (d) => [d.lng, d.lat],
          getRadius: (d) => 200 + (60 - (minute - d.minute)) * 12,
          radiusUnits: "meters",
          stroked: true,
          filled: false,
          getLineColor: (d) =>
            withAlpha([244, 114, 182], (60 - (minute - d.minute)) / 90),
          lineWidthMinPixels: 1.5,
        })
      );
    }
  }
  if (timeline.edges?.length) {
    layers.push(
      new LineLayer({
        id: "replay-cascade-edges",
        data: timeline.edges,
        getSourcePosition: (e) => [e.from_lng, e.from_lat],
        getTargetPosition: (e) => [e.to_lng, e.to_lat],
        getColor: (e) => withAlpha([56, 189, 248], 0.25 + 0.45 * (e.prob || 0)),
        getWidth: (e) => 1 + (e.prob || 0) * 3,
        widthUnits: "pixels",
      })
    );
  }
  return layers;
}

/** Deployment arcs from station -> deployment point. */
export function deploymentLayer({ deployment }) {
  if (!deployment?.length) return null;
  return new ArcLayer({
    id: "deployment-arcs",
    data: deployment,
    getSourcePosition: (d) => [d.station_lng, d.station_lat],
    getTargetPosition: (d) => [d.deploy_lng, d.deploy_lat],
    getSourceColor: (d) => (d.kind === "primary" ? [56, 189, 248] : [244, 114, 182]),
    getTargetColor: (d) => (d.kind === "primary" ? [251, 191, 36] : [248, 113, 113]),
    getWidth: (d) => 2 + d.officers * 1.2,
    widthUnits: "pixels",
    pickable: true,
    greatCircle: false,
  });
}

/** Barricade pins. */
export function barricadeLayer({ barricades }) {
  if (!barricades?.length) return null;
  return new ScatterplotLayer({
    id: "barricades",
    data: barricades,
    getPosition: (d) => [d.lng, d.lat],
    getFillColor: [251, 191, 36, 230],
    getRadius: 90,
    radiusMinPixels: 4,
    stroked: true,
    getLineColor: [255, 255, 255, 220],
  });
}

/** Diversion alternate corridors (lines). */
export function diversionLayer({ diversions }) {
  if (!diversions?.length) return null;
  const features = {
    type: "FeatureCollection",
    features: diversions.map((d, i) => ({
      type: "Feature",
      geometry: { type: "LineString", coordinates: d.geometry },
      properties: { ...d, i },
    })),
  };
  return new GeoJsonLayer({
    id: "diversions",
    data: features,
    stroked: true,
    filled: false,
    getLineColor: [34, 211, 238, 230],
    lineWidthMinPixels: 3,
    lineWidthMaxPixels: 5,
    pickable: true,
    extensions: [],
  });
}

/** Cascade nodes (police stations) glow base layer. */
export function cascadeBaseLayer({ nodes, hour, opacity = 0.35 }) {
  if (!nodes?.length) return null;
  return new ScatterplotLayer({
    id: "cascade-base",
    data: nodes,
    getPosition: (d) => [d.lng, d.lat],
    getFillColor: [56, 189, 248, Math.round(255 * opacity)],
    getRadius: (d) => 80 + Math.sqrt(d.count) * 9,
    radiusMinPixels: 3,
    radiusMaxPixels: 18,
  });
}
