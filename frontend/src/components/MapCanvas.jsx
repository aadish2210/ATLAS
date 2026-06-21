import React, { useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import maplibregl from "maplibre-gl";
import {
  corridorLayer,
  corridorGlowLayer,
  stationLayer,
  cascadeLayers,
  deploymentLayer,
  barricadeLayer,
  diversionLayer,
  cascadeBaseLayer,
  eventPinLayers,
  replayLayers,
} from "../layers";
import { useAnimatedT } from "../hooks/useAnimation";

const INITIAL_VIEW = {
  longitude: 77.594,
  latitude: 12.978,
  zoom: 11.2,
  pitch: 38,
  bearing: -8,
};

// Free dark Carto raster tiles — no token required.
const MAP_STYLE = {
  version: 8,
  sources: {
    "raster-tiles": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [
    {
      id: "raster",
      type: "raster",
      source: "raster-tiles",
      minzoom: 0,
      maxzoom: 22,
    },
  ],
};


export default function MapCanvas({
  corridors,
  corridorState,
  stations,
  cascadeNodes,
  pin,
  hour,
  showStations,
  showCascadeBase,
  simulation,
  replayTimeline,
  replayMinute,
  onMapClick,
  onTooltip,
}) {
  const [viewState, setViewState] = useState(INITIAL_VIEW);
  // Only animate when there is actually something animating (a dropped pin or
  // an active simulation). Idle map = no ticks = no wasted re-renders.
  const ripple = useAnimatedT(2400, 10, Boolean(pin || simulation));

  const layers = useMemo(() => {
    const ls = [];
    const gl = corridorGlowLayer({ corridors, corridorState, hour });
    if (gl) ls.push(gl);
    const cl = corridorLayer({ corridors, corridorState, hour });
    if (cl) ls.push(cl);

    const pinLs = eventPinLayers({ pin, t: ripple });
    ls.push(...pinLs);

    if (showCascadeBase) {
      const c = cascadeBaseLayer({ nodes: cascadeNodes, hour });
      if (c) ls.push(c);
    }
    if (showStations) {
      const s = stationLayer({ stations, hour });
      if (s) ls.push(s);
    }

    if (simulation) {
      const seed = { lat: simulation.request.lat, lng: simulation.request.lng };
      const cas = cascadeLayers({ seed, ripple: simulation.cascade, t: ripple });
      ls.push(...cas);
      const dep = deploymentLayer({ deployment: simulation.deployment });
      if (dep) ls.push(dep);
      const bar = barricadeLayer({ barricades: simulation.barricades });
      if (bar) ls.push(bar);
      const div = diversionLayer({ diversions: simulation.diversions });
      if (div) ls.push(div);
    }

    if (replayTimeline) {
      ls.push(...replayLayers({ timeline: replayTimeline, minute: replayMinute ?? 0 }));
    }
    return ls;
  }, [
    corridors,
    corridorState,
    hour,
    pin,
    showCascadeBase,
    cascadeNodes,
    showStations,
    stations,
    simulation,
    replayTimeline,
    replayMinute,
    ripple,
  ]);

  useEffect(() => {
    if (!pin) return;
    setViewState((prev) => ({
      ...prev,
      longitude: pin.lng,
      latitude: pin.lat,
      zoom: Math.max(prev.zoom, 13),
    }));
  }, [pin]);

  const handleClick = (info) => {
    if (!onMapClick) return;
    if (info.coordinate) {
      onMapClick({ lng: info.coordinate[0], lat: info.coordinate[1], info });
    }
  };

  const getTooltip = ({ object, layer }) => {
    if (!object || !layer) return null;
    if (layer.id === "stations") {
      return {
        html: `<div class="tooltip-card"><strong>${object.name}</strong><br/>
          ${object.events} events · median resp ${
          object.median_response_min?.toFixed?.(0) ?? "—"
        } min</div>`,
      };
    }
    if (layer.id === "cascade-zones") {
      return {
        html: `<div class="tooltip-card">
          <strong>Impact zone #${object.rank ?? "?"}</strong><br/>
          ${object.from} → <strong>${object.to}</strong><br/>
          ${Math.round(object.prob * 100)}% likelihood · expected within ${Math.round(object.delay_min)} min</div>`,
      };
    }
    if (layer.id === "deployment-arcs") {
      return {
        html: `<div class="tooltip-card"><strong>${object.station}</strong> → deployment<br/>
          ${object.officers} officer(s) · ETA ${object.eta_min.toFixed(0)} min</div>`,
      };
    }
    if (layer.id === "event-pin-core") {
      return {
        html: `<div class="tooltip-card"><strong>Manual event pin</strong><br/>Click Simulate impact to run a live forecast.</div>`,
      };
    }
    if (layer.id === "diversions") {
      return {
        html: `<div class="tooltip-card"><strong>Diversion: ${object.properties.corridor}</strong><br/>
          residual load ~${object.properties.predicted_residual_pct}%</div>`,
      };
    }
    if (layer.id === "corridors") {
      const name = object.properties.name;
      const st = corridorState?.[name];
      return {
        html: `<div class="tooltip-card"><strong>${name}</strong><br/>
          ${object.properties.events} events · predictability ${(
          (st?.predictability ?? 0) * 100
        ).toFixed(0)}% · ESI ${(st?.esi_by_hour?.[hour] ?? 0).toFixed(1)}</div>`,
      };
    }
    return null;
  };

  return (
    <div className="map-container">
      <BasemapMap viewState={viewState} />
      <DeckGL
        style={{ position: "absolute", inset: 0, zIndex: 2 }}
        viewState={viewState}
        controller={true}
        onViewStateChange={({ viewState }) => setViewState(viewState)}
        layers={layers}
        onClick={handleClick}
        getTooltip={getTooltip}
      />
    </div>
  );
}


/**
 * Tiny MapLibre wrapper that renders a basemap inside DeckGL. We avoid
 * react-map-gl because the version that supports MapLibre (>=7.1) is not
 * available on the corp npm registry.
 */
function BasemapMap({ viewState }) {
  const ref = useRef(null);
  const map = useRef(null);
  useEffect(() => {
    if (!ref.current || map.current) return;
    map.current = new maplibregl.Map({
      container: ref.current,
      style: MAP_STYLE,
      center: [viewState.longitude, viewState.latitude],
      zoom: viewState.zoom,
      pitch: viewState.pitch,
      bearing: viewState.bearing,
      attributionControl: false,
      interactive: false,
    });
    return () => {
      map.current?.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!map.current) return;
    map.current.jumpTo({
      center: [viewState.longitude, viewState.latitude],
      zoom: viewState.zoom,
      pitch: viewState.pitch,
      bearing: viewState.bearing,
    });
  }, [viewState]);

  return (
    <div
      className="basemap-layer"
      ref={ref}
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 1,
        pointerEvents: "none",
      }}
    />
  );
}
