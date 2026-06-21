import React, { useEffect, useMemo, useState } from "react";
import MapCanvas from "./components/MapCanvas";
import EventDropPanel from "./components/EventDropPanel";
import ForecastPanel from "./components/ForecastPanel";
import KpiBar from "./components/KpiBar";
import CopilotPanel from "./components/CopilotPanel";
import FingerprintClock from "./components/FingerprintClock";
import AuditRibbon from "./components/AuditRibbon";
import InsightsPanel from "./components/InsightsPanel";
import ReplayPanel from "./components/ReplayPanel";
import { api } from "./api/client";

const TABS = [
  { key: "ops", label: "Ops" },
  { key: "replay", label: "Replay" },
  { key: "insights", label: "Insights" },
  { key: "fingerprint", label: "Fingerprint" },
  { key: "audit", label: "Audit" },
  { key: "copilot", label: "Co-pilot" },
];

export default function App() {
  const [tab, setTab] = useState("ops");
  const [city, setCity] = useState(null);
  const [audit, setAudit] = useState(null);
  const [corridors, setCorridors] = useState(null);
  const [corridorState, setCorridorState] = useState(null);
  const [stations, setStations] = useState(null);
  const [cascade, setCascade] = useState(null);
  const [fp, setFp] = useState(null);

  const [pin, setPin] = useState(null); // {lat, lng}
  const [eventState, setEventState] = useState({
    event_kind: "rally",
    expected_size: "medium",
    duration_min: 90,
    requires_road_closure: false,
  });
  const [simulation, setSimulation] = useState(null);
  const [busy, setBusy] = useState(false);
  const [replayTimeline, setReplayTimeline] = useState(null);
  const [replayMinute, setReplayMinute] = useState(0);
  const [legendOpen, setLegendOpen] = useState(true);

  const hour = new Date().getHours();

  useEffect(() => {
    (async () => {
      try {
        const [c, a, cs, st, ca, fpRes, corr] = await Promise.all([
          api.city(),
          api.audit(),
          api.corridorState(),
          api.stations(),
          api.cascade(),
          api.fingerprint(),
          api.corridors(),
        ]);
        setCity(c);
        setAudit(a);
        setCorridorState(cs);
        setStations(st.stations || []);
        setCascade(ca);
        setFp(fpRes);
        setCorridors(corr);
      } catch (e) {
        console.error("Bootstrap failed", e);
      }
    })();
  }, []);

  const handleMapClick = ({ lat, lng }) => {
    setPin({ lat, lng });
    setSimulation(null);
  };

  const handleSetPin = ({ lat, lng }) => {
    setPin({ lat, lng });
    setSimulation(null);
  };

  const handleSimulate = async () => {
    if (!pin) return;
    setBusy(true);
    try {
      const sim = await api.simulate({
        ...eventState,
        lat: pin.lat,
        lng: pin.lng,
      });
      setSimulation(sim);
    } catch (e) {
      console.error("Simulate failed", e);
    } finally {
      setBusy(false);
    }
  };

  const handleClear = () => {
    setPin(null);
    setSimulation(null);
  };

  const cityFp = fp?.city;

  const showStations = tab === "ops" || tab === "audit";
  const showCascadeBase = tab === "ops" && simulation == null;
  const inReplay = tab === "replay";

  return (
    <div className="app-shell">
      <MapCanvas
        corridors={corridors}
        corridorState={corridorState}
        stations={stations}
        cascadeNodes={cascade?.nodes}
        pin={pin}
        hour={hour}
        showStations={showStations && !inReplay}
        showCascadeBase={showCascadeBase && !inReplay}
        simulation={inReplay ? null : simulation}
        replayTimeline={inReplay ? replayTimeline : null}
        replayMinute={replayMinute}
        onMapClick={handleMapClick}
      />

      <div className={"map-legend" + (legendOpen ? " open" : "")}>
        <button
          className="legend-toggle"
          onClick={() => setLegendOpen((v) => !v)}
          title="Toggle map legend"
        >
          <span className="legend-dot-cluster">
            <i className="swatch green" />
            <i className="swatch yellow" />
            <i className="swatch red" />
          </span>
          <span className="legend-title">Legend</span>
          <span className="legend-caret">{legendOpen ? "−" : "+"}</span>
        </button>
        {legendOpen && (
          <div className="legend-body">
            <div className="legend-row"><span className="swatch green" /> Smooth corridor</div>
            <div className="legend-row"><span className="swatch yellow" /> Slowing</div>
            <div className="legend-row"><span className="swatch red" /> Congested</div>
            <div className="legend-row"><span className="swatch pink" /> Your event pin</div>
            <div className="legend-row"><span className="swatch cyan" /> Officer deployment</div>
            <div className="legend-hint">
              After simulating, numbered circles are predicted secondary impact
              zones (likelihood · ETA). #1 = most likely.
            </div>
          </div>
        )}
      </div>

      <div className="topbar">
        <div className="brand">
          <div className="logo">A</div>
          <div>
            <h1>ATLAS</h1>
            <div className="tag">Astram-Trained · Live · Adaptive</div>
          </div>
        </div>
        <div className="kpi-bar">
          <KpiBar city={city} audit={audit} hour={hour} />
        </div>
      </div>

      <div className="toolbar">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={tab === t.key ? "active" : ""}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Left side */}
      {tab === "ops" && (
        <EventDropPanel
          pin={pin}
          state={eventState}
          onChange={setEventState}
          onSimulate={handleSimulate}
          onClear={handleClear}
          onSetPin={handleSetPin}
          busy={busy}
          hint={
            simulation
              ? `Simulated · cite ${cityFp?.events ?? "?"} historical events.`
              : pin
              ? "Click 'Simulate impact' when ready."
              : ""
          }
        />
      )}
      {tab === "fingerprint" && (
        <div className="side-panel left-panel">
          <div className="head">
            <h3>Behavioral fingerprint</h3>
            <span className="live-pill">learned</span>
          </div>
          <div className="body">
            {cityFp ? (
              <FingerprintClock
                breathing={cityFp.breathing}
                anomalyDays={cityFp.anomaly_days}
                predictability={cityFp.predictability}
                label="City-wide"
              />
            ) : (
              <div className="empty">Loading fingerprint...</div>
            )}
            <div className="divider" />
            <div className="muted small">
              The dial is the city's 24-hour rhythm — clear rush-hour peaks,
              quiet 2–5 AM, repeating every week. Red dots are surge days the
              model flagged on its own (no calendar): these line up with the
              city's <strong>festivals and rallies</strong>, learned purely
              from incident timestamps.
            </div>
          </div>
        </div>
      )}
      {tab === "audit" && (
        <div className="side-panel left-panel">
          <div className="head">
            <h3>Counterfactual audit</h3>
            <span className="live-pill">retro</span>
          </div>
          <div className="body">
            <div className="muted small">
              ATLAS replayed every audited incident. Below: avg response,
              officer-hours saved, P90 tail, and the equity Gini before/after.
            </div>
            <div className="divider" />
            {audit?.by_zone?.slice(0, 8).map((z, i) => (
              <div className="list-item" key={i}>
                <span className="pill">−{z.delta.toFixed(1)} min</span>
                <strong>{z.zone}</strong>
                <div className="meta">
                  baseline {z.baseline_avg.toFixed(1)} → ATLAS{" "}
                  {z.atlas_avg.toFixed(1)} (n={z.n})
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {tab === "copilot" && (
        <div className="side-panel left-panel">
          <div className="head">
            <h3>Co-pilot</h3>
            <span className="live-pill">grounded</span>
          </div>
          <div className="body">
            <CopilotPanel />
          </div>
        </div>
      )}
      {tab === "insights" && (
        <div className="side-panel left-panel">
          <div className="head">
            <h3>Proof &amp; insights</h3>
            <span className="live-pill">backtest</span>
          </div>
          <div className="body">
            <InsightsPanel />
          </div>
        </div>
      )}
      {tab === "replay" && (
        <div className="side-panel left-panel">
          <div className="head">
            <h3>Time-machine replay</h3>
            <span className="live-pill">history</span>
          </div>
          <div className="body">
            <ReplayPanel
              onTimeline={setReplayTimeline}
              onTick={setReplayMinute}
            />
          </div>
        </div>
      )}

      {/* Right side */}
      {tab === "ops" && (
        <ForecastPanel simulation={simulation} evidenceCount={cityFp?.events ?? 0} />
      )}
      {tab === "fingerprint" && (
        <div className="side-panel right-panel">
          <div className="head">
            <h3>Drainage Vulnerability Index</h3>
            <span className="live-pill">DVI</span>
          </div>
          <div className="body">
            <div className="muted small">
              % of events at each zone tagged with weather/water-logging
              keywords from descriptions. Critical zones load more during
              storm-stress conditions.
            </div>
            <div className="divider" />
            {fp?.dvi &&
              Object.entries(fp.dvi)
                .sort(([, a], [, b]) => b.weather_share - a.weather_share)
                .map(([zone, d]) => (
                  <div className="list-item" key={zone}>
                    <span
                      className={
                        "pill " +
                        (d.category === "Critical"
                          ? "danger"
                          : d.category === "Moderate"
                          ? "warn"
                          : "")
                      }
                    >
                      {d.category}
                    </span>
                    <strong>{zone}</strong>
                    <div className="meta">
                      {(d.weather_share * 100).toFixed(1)}% weather share · n=
                      {d.events}
                    </div>
                  </div>
                ))}
          </div>
        </div>
      )}
      {tab === "audit" && (
        <div className="side-panel right-panel">
          <div className="head">
            <h3>Audit summary</h3>
          </div>
          <div className="body">
            <div className="esi-card">
              <div className="label">Officer-hours saved (extrapolated)</div>
              <div className="esi-value">
                {audit?.officer_hours_saved?.toFixed(1) ?? "—"}
              </div>
              <div className="esi-band">
                avg response {audit?.baseline?.avg_response_min?.toFixed(1) ?? "—"} →{" "}
                {audit?.atlas?.avg_response_min?.toFixed(1) ?? "—"} min · worst-case
                (P90) {audit?.baseline?.p90_response_min?.toFixed(1) ?? "—"} →{" "}
                {audit?.atlas?.p90_response_min?.toFixed(1) ?? "—"} min
              </div>
            </div>
            <div className="muted small">
              <strong>Methodology:</strong> sample of {audit?.n_sample}{" "}
              historical incidents replayed under (a) the actual station
              assignment and (b) ATLAS's nearest-station-with-load policy. The
              delta is extrapolated to the full {audit?.n_events_audited}-event
              audit set. Response times are modelled estimates (distance +
              station load), not GPS-measured.
            </div>
            <div className="divider" />
            <div className="muted small">
              {(() => {
                const b = audit?.gini_baseline;
                const a = audit?.gini_atlas;
                if (b == null || a == null) return null;
                const delta = a - b;
                if (Math.abs(delta) < 0.005) {
                  return (
                    <>
                      Equity across zones (Gini) is essentially unchanged
                      (<strong>{b.toFixed(3)}</strong> →{" "}
                      <strong>{a.toFixed(3)}</strong>) — ATLAS improves speed
                      without making zone fairness worse.
                    </>
                  );
                }
                return delta < 0 ? (
                  <>
                    Equity across zones (Gini) improved from{" "}
                    <strong>{b.toFixed(3)}</strong> to{" "}
                    <strong>{a.toFixed(3)}</strong> — faster <em>and</em> fairer.
                  </>
                ) : (
                  <>
                    Equity across zones (Gini) shifted slightly from{" "}
                    <strong>{b.toFixed(3)}</strong> to{" "}
                    <strong>{a.toFixed(3)}</strong> — roughly neutral on
                    fairness; the gain here is speed.
                  </>
                );
              })()}
            </div>
          </div>
        </div>
      )}
      {tab === "copilot" && (
        <div className="side-panel right-panel">
          <div className="head">
            <h3>How the co-pilot stays honest</h3>
          </div>
          <div className="body">
            <ul className="muted small" style={{ paddingLeft: 18, lineHeight: 1.7 }}>
              <li>Every numerical claim is a SQL-style query against the dataset.</li>
              <li>If filters resolve zero rows, the co-pilot refuses.</li>
              <li>Citations show row counts and the exact filter trace.</li>
              <li>No external LLM. No data leaves the building.</li>
            </ul>
          </div>
        </div>
      )}

      {/* Bottom audit ribbon */}
      <div className="side-panel bottom-panel">
        <div className="body" style={{ padding: 14 }}>
          <AuditRibbon audit={audit} />
        </div>
      </div>
    </div>
  );
}
