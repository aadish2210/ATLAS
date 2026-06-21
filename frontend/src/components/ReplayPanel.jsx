import React, { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";

const ANOMALY_DAYS = [
  "2024-03-07",
  "2023-12-16",
  "2024-04-06",
  "2024-03-26",
  "2024-03-29",
  "2024-01-17",
  "2024-03-08",
];

export default function ReplayPanel({ onTimeline, onTick }) {
  const [date, setDate] = useState(ANOMALY_DAYS[0]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [minute, setMinute] = useState(0);
  const [speed, setSpeed] = useState(15);
  const lastTimeRef = useRef(0);

  // Load timeline whenever the date changes
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const r = await api.replay(date);
        if (cancelled) return;
        setData(r);
        setMinute(0);
        onTimeline?.(r);
      } catch (e) {
        console.error("replay load failed", e);
      } finally {
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [date, onTimeline]);

  // Animation loop driven by requestAnimationFrame, throttled to ~12 fps so
  // the deck.gl layers don't rebuild 60 times a second during playback.
  useEffect(() => {
    if (!playing || !data) return;
    let raf;
    lastTimeRef.current = performance.now();
    let lastPush = 0;
    const tick = (now) => {
      const dt = (now - lastTimeRef.current) / 1000;
      if (now - lastPush >= 1000 / 12) {
        lastPush = now;
        lastTimeRef.current = now;
        setMinute((m) => {
          const next = m + dt * speed;
          if (next >= 24 * 60) {
            setPlaying(false);
            return 24 * 60 - 1;
          }
          return next;
        });
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, data, speed]);

  // Push current minute up to the parent so the map can filter
  useEffect(() => {
    onTick?.(minute);
  }, [minute, onTick]);

  const fired = useMemo(() => {
    if (!data?.events) return [];
    return data.events.filter((e) => e.minute <= minute);
  }, [data, minute]);

  const hh = Math.floor(minute / 60).toString().padStart(2, "0");
  const mm = Math.floor(minute % 60).toString().padStart(2, "0");

  const causeCounts = useMemo(() => {
    const m = new Map();
    for (const e of fired) m.set(e.cause, (m.get(e.cause) || 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [fired]);

  return (
    <div className="copilot" style={{ gap: 12 }}>
      <div className="row">
        <label>Date</label>
        <select value={date} onChange={(e) => setDate(e.target.value)}>
          {ANOMALY_DAYS.map((d) => (
            <option key={d} value={d}>
              {d} (anomaly)
            </option>
          ))}
        </select>
      </div>

      <div className="row">
        <label>Speed</label>
        <select
          value={speed}
          onChange={(e) => setSpeed(Number(e.target.value))}
        >
          <option value={5}>5× (slow)</option>
          <option value={15}>15×</option>
          <option value={30}>30×</option>
          <option value={60}>60× (fast)</option>
        </select>
      </div>

      <div className="actions">
        <button
          className="primary"
          onClick={() => setPlaying((p) => !p)}
          disabled={loading || !data?.events?.length}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <button
          onClick={() => {
            setMinute(0);
            setPlaying(false);
          }}
        >
          Reset
        </button>
      </div>

      <div className="esi-card" style={{ marginTop: 4 }}>
        <div className="label">Time of day (IST)</div>
        <div className="esi-value">
          {hh}:{mm}
        </div>
        <div className="esi-band">
          Fired {fired.length} of {data?.events?.length ?? 0} incidents
          {data?.n_edges != null && (
            <span> · {data.n_edges} cascade edges among active stations</span>
          )}
        </div>
      </div>

      <input
        type="range"
        min={0}
        max={24 * 60 - 1}
        step={1}
        value={Math.min(minute, 24 * 60 - 1)}
        onChange={(e) => setMinute(Number(e.target.value))}
      />

      {causeCounts.length > 0 && (
        <>
          <div className="section-title">
            <span className="dot" />
            Cause breakdown so far
          </div>
          {causeCounts.slice(0, 6).map(([c, n]) => (
            <div className="list-item" key={c}>
              <span className="pill">{n}</span>
              <strong>{c}</strong>
            </div>
          ))}
        </>
      )}

      <div className="muted small">
        Time-lapse uses real timestamps from the dataset. Edges shown are
        cascade-graph predictions among stations active that day —
        operators would see them in the morning, not after the fact.
      </div>
    </div>
  );
}
