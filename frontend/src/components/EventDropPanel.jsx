import React, { useMemo, useState } from "react";
import { api } from "../api/client";

const KINDS = [
  { value: "rally", label: "Political rally" },
  { value: "festival", label: "Festival / Procession" },
  { value: "sports_match", label: "Sports match" },
  { value: "vip_movement", label: "VIP movement" },
  { value: "procession", label: "Procession" },
  { value: "construction", label: "Construction zone" },
  { value: "protest", label: "Protest" },
];

const SIZES = [
  { value: "small", label: "Small (<5K)" },
  { value: "medium", label: "Medium (5-25K)" },
  { value: "large", label: "Large (25K+)" },
];

export default function EventDropPanel({
  pin,
  state,
  onChange,
  onSimulate,
  onClear,
  onSetPin,
  busy,
  hint,
}) {
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState([]);
  const [searchError, setSearchError] = useState("");

  const coordMatch = useMemo(() => {
    const m = query.trim().match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
    if (!m) return null;
    const lat = Number(m[1]);
    const lng = Number(m[2]);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
    return { lat, lng };
  }, [query]);

  const doSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setSearchError("");
    if (coordMatch) {
      onSetPin?.(coordMatch);
      setResults([]);
      return;
    }
    setSearching(true);
    try {
      const r = await api.geocode(q);
      const cleaned = (r || []).slice(0, 5).map((row) => ({
        label: row.display_name,
        lat: Number(row.lat),
        lng: Number(row.lon),
      }));
      setResults(cleaned.filter((x) => Number.isFinite(x.lat) && Number.isFinite(x.lng)));
      if (!cleaned.length) {
        setSearchError("No matches. Try a nearby landmark or a lat,lng pair.");
      }
    } catch (e) {
      setSearchError("Search failed. You can still click on map or type lat,lng.");
    } finally {
      setSearching(false);
    }
  };

  const placeResult = (item) => {
    onSetPin?.({ lat: item.lat, lng: item.lng });
    setQuery(item.label);
    setResults([]);
    setSearchError("");
  };

  return (
    <div className="side-panel left-panel drop-panel">
      <div className="head">
        <h3>Drop an event</h3>
        <span className="live-pill">simulator</span>
      </div>
      <div className="body">
        <div className="section-title" style={{ marginTop: 0 }}>
          <span className="dot" />
          Pick location
        </div>
        <div className="search-row">
          <input
            value={query}
            placeholder="Search place or type 12.9716, 77.5946"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") doSearch();
            }}
          />
          <button onClick={doSearch} disabled={searching}>
            {searching ? "..." : "Find"}
          </button>
        </div>
        {searchError && <div className="muted small" style={{ marginTop: 6 }}>{searchError}</div>}
        {results.length > 0 && (
          <div className="search-results">
            {results.map((r) => (
              <button key={`${r.lat}-${r.lng}-${r.label}`} className="search-hit" onClick={() => placeResult(r)}>
                {r.label}
              </button>
            ))}
          </div>
        )}

        {!pin && (
          <div className="empty">
            <div className="icon">⊕</div>
            Click anywhere on the map or use search above.
            ATLAS will animate ripple impact and forecast cascading congestion,
            manpower, barricades, and diversions.
          </div>
        )}
        {pin && (
          <>
            <div className="row">
              <label>Location</label>
              <span className="coord-pill">
                {pin.lat.toFixed(4)}, {pin.lng.toFixed(4)}
              </span>
            </div>
            <div className="row">
              <label>Type</label>
              <select
                value={state.event_kind}
                onChange={(e) =>
                  onChange({ ...state, event_kind: e.target.value })
                }
              >
                {KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="row">
              <label>Size</label>
              <select
                value={state.expected_size}
                onChange={(e) =>
                  onChange({ ...state, expected_size: e.target.value })
                }
              >
                {SIZES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="row">
              <label>Duration</label>
              <input
                type="number"
                min={5}
                max={1440}
                value={state.duration_min}
                onChange={(e) =>
                  onChange({
                    ...state,
                    duration_min: Number(e.target.value) || 60,
                  })
                }
              />
            </div>
            <div className="row">
              <label>Closure</label>
              <select
                value={state.requires_road_closure ? "yes" : "no"}
                onChange={(e) =>
                  onChange({
                    ...state,
                    requires_road_closure: e.target.value === "yes",
                  })
                }
              >
                <option value="no">Not required</option>
                <option value="yes">Required</option>
              </select>
            </div>
            <div className="actions">
              <button
                className="primary"
                onClick={onSimulate}
                disabled={busy}
              >
                {busy ? "Simulating..." : "Simulate impact"}
              </button>
              <button onClick={onClear} className="danger">
                Clear
              </button>
            </div>
          </>
        )}
        <div className="divider" />
        <div className="muted small" style={{ lineHeight: 1.7 }}>
          Quick guide: 1) place pin, 2) set event type/size, 3) press Simulate impact.
        </div>
        {hint && <div className="cite-trace" style={{ marginTop: 12 }}>{hint}</div>}
      </div>
    </div>
  );
}
