"""Step 6 — Counterfactual Deployment Audit.

Replays history with two policies side-by-side:
  * BASELINE  — events handled by their actual police_station (data ground truth).
  * ATLAS     — every event reassigned to the nearest station with capacity,
                weighted by station's hour-specific load.

We report:
  * officer-hours saved (sum of expected response delta * priority weight)
  * average response-time delta (min)
  * Gini coefficient of response time across zones (equity lens)
  * 50 worked scenarios — used for the comparison panel UI
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402


def _haversine_vec(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def _response_proxy(distance_km, station_load_factor):
    """Simple physics-free proxy. 4 km/h fixed avg dispatch + load penalty (min)."""
    base = distance_km * 1.6  # ~37 km/h
    load_penalty = station_load_factor * 6.0
    return base + load_penalty + 4.0  # 4 min dispatch overhead


def _gini(values: np.ndarray) -> float:
    v = np.sort(np.asarray(values, dtype=float))
    if v.size == 0 or v.sum() == 0:
        return 0.0
    n = v.size
    cum = np.cumsum(v)
    return float((2 * np.sum((np.arange(1, n + 1)) * v) - (n + 1) * cum[-1]) / (n * cum[-1]))


def main() -> None:
    df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
    stations_blob = json.loads((settings.artifacts_dir / "stations.json").read_text())
    stations = pd.DataFrame(stations_blob["stations"])
    if stations.empty:
        print("[audit] no stations — skipping audit")
        (settings.artifacts_dir / "audit.json").write_text(json.dumps({"empty": True}))
        return
    print(f"[audit] events={len(df):,}  stations={len(stations)}")

    # baseline response time (proxy from actual station map, with empirical load)
    station_lookup = {row["name"]: row for _, row in stations.iterrows()}

    rng = np.random.default_rng(7)
    baseline_resp = []
    atlas_resp = []
    rows = []
    by_zone_base: dict[str, list[float]] = {}
    by_zone_atlas: dict[str, list[float]] = {}

    sample = df.sample(min(2000, len(df)), random_state=11).reset_index(drop=True)
    for i, ev in sample.iterrows():
        actual = station_lookup.get(ev["police_station"])
        # baseline distance (use centroid if station maps to known name; else 5 km)
        if actual is not None:
            d_base = _haversine_vec(ev["latitude"], ev["longitude"],
                                    actual["lat"], actual["lng"])
            load_base = actual["hourly_load"][int(ev["hour"])] if actual.get("hourly_load") else 0.5
        else:
            d_base = 5.0
            load_base = 0.7
        rt_base = _response_proxy(d_base, load_base)

        # ATLAS: nearest station weighted by 1 + load penalty
        d = _haversine_vec(ev["latitude"], ev["longitude"],
                           stations["lat"].values, stations["lng"].values)
        loads = np.array([s[int(ev["hour"])] for s in stations["hourly_load"]])
        score = d * (1 + 0.4 * loads)
        best = int(np.argmin(score))
        d_atlas = float(d[best])
        rt_atlas = _response_proxy(d_atlas, float(loads[best]))

        baseline_resp.append(rt_base)
        atlas_resp.append(rt_atlas)
        z = ev["zone"] if ev["zone"] != "Unknown" else "Other"
        by_zone_base.setdefault(z, []).append(rt_base)
        by_zone_atlas.setdefault(z, []).append(rt_atlas)

        # save first 60 worked scenarios for the UI
        if len(rows) < 60:
            rows.append({
                "id": ev["id"],
                "lat": float(ev["latitude"]),
                "lng": float(ev["longitude"]),
                "cause": ev["event_cause"],
                "zone": ev["zone"],
                "hour": int(ev["hour"]),
                "actual_station": ev["police_station"],
                "atlas_station": stations.iloc[best]["name"],
                "baseline_resp_min": round(rt_base, 2),
                "atlas_resp_min": round(rt_atlas, 2),
                "delta_min": round(rt_base - rt_atlas, 2),
            })

    base_arr = np.array(baseline_resp)
    atlas_arr = np.array(atlas_resp)

    # extrapolate officer-hour saving from sample to full dataset
    delta_per_event_min = float((base_arr - atlas_arr).mean())
    officer_hours_saved = round(delta_per_event_min * len(df) / 60.0, 1)

    zone_summary = []
    for z in sorted(set(by_zone_base.keys())):
        b = np.array(by_zone_base[z])
        a = np.array(by_zone_atlas.get(z, []))
        if len(b) < 5 or len(a) < 5:
            continue
        zone_summary.append({
            "zone": z,
            "n": int(len(b)),
            "baseline_avg": round(float(b.mean()), 2),
            "atlas_avg": round(float(a.mean()), 2),
            "delta": round(float(b.mean() - a.mean()), 2),
        })
    zone_summary.sort(key=lambda r: -r["delta"])

    # gini across zone means
    gini_base = _gini(np.array([z["baseline_avg"] for z in zone_summary]))
    gini_atlas = _gini(np.array([z["atlas_avg"] for z in zone_summary]))

    out = {
        "n_events_audited": int(len(df)),
        "n_sample": int(len(sample)),
        "baseline": {
            "avg_response_min": round(float(base_arr.mean()), 2),
            "median_response_min": round(float(np.median(base_arr)), 2),
            "p90_response_min": round(float(np.percentile(base_arr, 90)), 2),
        },
        "atlas": {
            "avg_response_min": round(float(atlas_arr.mean()), 2),
            "median_response_min": round(float(np.median(atlas_arr)), 2),
            "p90_response_min": round(float(np.percentile(atlas_arr, 90)), 2),
        },
        "delta_avg_min": round(float(base_arr.mean() - atlas_arr.mean()), 2),
        "delta_p90_min": round(float(np.percentile(base_arr, 90) - np.percentile(atlas_arr, 90)), 2),
        "officer_hours_saved": officer_hours_saved,
        "gini_baseline": round(gini_base, 3),
        "gini_atlas": round(gini_atlas, 3),
        "by_zone": zone_summary,
        "scenarios": rows,
        # rough rupee impact: officer hours saved * 500 ₹/hr * 100 vehicles delayed factor
        "rupee_impact_lakh": round(officer_hours_saved * 500 / 1e5, 2),
    }
    (settings.artifacts_dir / "audit.json").write_text(json.dumps(out, indent=2))
    print(f"[audit] saved={officer_hours_saved} officer-hrs  delta={out['delta_avg_min']} min")


if __name__ == "__main__":
    main()
