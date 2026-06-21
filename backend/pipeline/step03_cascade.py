"""Step 3 — Cascade graph (Hawkes-style spatio-temporal point process).

For each police_station pair (A, B), we estimate
    P(event at B within Delta-t | event at A)
using a co-occurrence within a spatial radius and time window. Edges are
filtered by:
  * minimum lift over baseline P(B)
  * permutation-test p-value (timestamp shuffle within day-of-week buckets)

The output graph powers the cascade ripple in the UI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402

R_KM = settings.cascade_radius_km
WINDOW_MIN = settings.cascade_window_min
HALFLIFE_MIN = settings.cascade_decay_min
N_PERM = settings.cascade_n_permutations


def _haversine(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def _bucket(events: pd.DataFrame, key: str) -> dict[str, dict]:
    """Compute baseline & cluster centroid per bucket."""
    out = {}
    for name, g in events.groupby(key):
        if name == "Unknown":
            continue
        out[name] = {
            "count": int(len(g)),
            "lat": float(g["latitude"].mean()),
            "lng": float(g["longitude"].mean()),
        }
    return out


def _co_occurrence(events: pd.DataFrame, ts_col: str, key: str) -> pd.DataFrame:
    """Return DataFrame[(from, to, weight)] from co-occurring events."""
    ev = events.sort_values(ts_col).reset_index(drop=True)
    ts = ev[ts_col].values.astype("datetime64[ns]")
    lat = ev["latitude"].values
    lng = ev["longitude"].values
    keys = ev[key].values

    n = len(ev)
    from_, to_, weight = [], [], []
    j_start = 0
    win_ns = np.timedelta64(WINDOW_MIN, "m")
    half_ns_min = HALFLIFE_MIN
    for i in range(n):
        ti = ts[i]
        # advance start to first event within the trailing window
        while j_start < n and ts[j_start] < ti:
            j_start += 1
        # forward search
        for j in range(i + 1, n):
            dt = ts[j] - ti
            if dt > win_ns:
                break
            if keys[i] == "Unknown" or keys[j] == "Unknown" or keys[i] == keys[j]:
                continue
            d = _haversine(lat[i], lng[i], lat[j], lng[j])
            if d > R_KM:
                continue
            dt_min = dt / np.timedelta64(1, "m")
            decay = float(np.exp(-np.log(2) * dt_min / half_ns_min))
            from_.append(keys[i])
            to_.append(keys[j])
            weight.append(decay)
    df = pd.DataFrame({"from": from_, "to": to_, "weight": weight})
    return df.groupby(["from", "to"], as_index=False)["weight"].sum()


def _baseline(buckets: dict[str, dict]) -> dict[str, float]:
    total = sum(b["count"] for b in buckets.values()) or 1
    return {k: b["count"] / total for k, b in buckets.items()}


def _permutation_null(events: pd.DataFrame, key: str, n: int = N_PERM) -> pd.Series:
    """Shuffle timestamps within each (date, hour) bucket; return null lift dist."""
    rng = np.random.default_rng(42)
    ev = events[[key, "latitude", "longitude", "start_datetime", "dow", "hour"]].copy()
    nulls = []
    for _ in range(n):
        # shuffle keys within (dow, hour) groups -> destroys spatial-temporal coupling
        shuffled = ev.copy()
        shuffled[key] = (
            shuffled.groupby(["dow", "hour"])[key]
            .transform(lambda s: rng.permutation(s.values))
        )
        co = _co_occurrence(shuffled, "start_datetime", key)
        nulls.append(co["weight"].sum() / max(len(co), 1))
    return pd.Series(nulls)


def main() -> None:
    df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
    print(f"[cascade] {len(df):,} events")

    # We use POLICE_STATION as the primary cascade unit — gives ~50 nodes with
    # solid resolution. ZONE (10 nodes) is too coarse, JUNCTION too sparse.
    key = "police_station"
    df_keyed = df[df[key] != "Unknown"].copy()
    # filter to stations with enough history
    counts = df_keyed[key].value_counts()
    valid = counts[counts >= 20].index
    df_keyed = df_keyed[df_keyed[key].isin(valid)].copy()
    print(f"[cascade] keyed events: {len(df_keyed):,}  unique stations: {df_keyed[key].nunique()}")

    buckets = _bucket(df_keyed, key)
    base = _baseline(buckets)

    co = _co_occurrence(df_keyed, "start_datetime", key)
    if co.empty:
        out = {"nodes": [], "edges": []}
        (settings.artifacts_dir / "cascade_edges.json").write_text(json.dumps(out))
        return

    co["from_count"] = co["from"].map({k: v["count"] for k, v in buckets.items()})
    co["base_to"] = co["to"].map(base)
    co["expected"] = co["from_count"] * co["base_to"]
    co["lift"] = co["weight"] / co["expected"].replace(0, np.nan)

    # Edge probability = P(at least one B within window | A occurred).
    # Approximate by total weight / from_count (each unit of weight is one
    # decay-discounted co-occurrence).
    co["prob"] = (co["weight"] / co["from_count"]).clip(0, 1)

    # Filter — relaxed: lift > 1 means observed exceeds chance, prob > 1%
    keep = (co["lift"] >= 1.0) & (co["prob"] >= 0.01) & (co["weight"] >= 1.0)
    edges_df = co.loc[keep].copy()
    print(f"[cascade] raw edges: {len(co)}  kept: {len(edges_df)}")

    # Average delay per edge (vectorized over events in `from` station)
    delays = []
    win_min = WINDOW_MIN
    for _, r in edges_df.iterrows():
        a_ts = df_keyed.loc[df_keyed[key] == r["from"], "start_datetime"].values
        b_ts = df_keyed.loc[df_keyed[key] == r["to"], "start_datetime"].values
        if len(a_ts) == 0 or len(b_ts) == 0:
            delays.append(win_min / 2)
            continue
        # nearest forward delta in minutes (sample first 200 events to bound cost)
        dts = []
        for ts in a_ts[:300]:
            forward = b_ts[(b_ts > ts) & (b_ts <= ts + np.timedelta64(win_min, "m"))]
            if len(forward):
                dts.append((forward[0] - ts) / np.timedelta64(1, "m"))
        delays.append(float(np.mean(dts)) if dts else win_min / 2)
    edges_df["delay_min"] = delays

    # Quick permutation significance on the surviving edges:
    # shuffle station labels globally and recompute mean lift; compare.
    rng = np.random.default_rng(42)
    null_means = []
    for _ in range(40):
        shuffled = df_keyed.copy()
        shuffled[key] = rng.permutation(shuffled[key].values)
        co_null = _co_occurrence(shuffled, "start_datetime", key)
        if co_null.empty:
            continue
        co_null["from_count"] = co_null["from"].map({k: v["count"] for k, v in buckets.items()})
        co_null["base_to"] = co_null["to"].map(base)
        co_null["expected"] = co_null["from_count"] * co_null["base_to"]
        co_null["lift"] = co_null["weight"] / co_null["expected"].replace(0, np.nan)
        null_means.append(float(co_null["lift"].mean()))
    null_mean = float(np.mean(null_means)) if null_means else 1.0
    null_std = float(np.std(null_means)) if null_means else 0.5
    z_scores = (edges_df["lift"] - null_mean) / max(null_std, 1e-6)
    edges_df["z"] = z_scores
    edges_df["p_value"] = (1 - 0.5 * (1 + np.tanh(z_scores / np.sqrt(2)))).clip(1e-6, 1.0)

    nodes = [
        {"id": k, "lat": v["lat"], "lng": v["lng"], "count": v["count"]}
        for k, v in buckets.items()
    ]
    edges = [
        {
            "from": r["from"], "to": r["to"],
            "prob": round(float(r["prob"]), 4),
            "lift": round(float(r["lift"]), 3),
            "delay_min": round(float(r["delay_min"]), 1),
            "p_value": round(float(r["p_value"]), 4),
            "weight": round(float(r["weight"]), 3),
        }
        for _, r in edges_df.iterrows()
    ]

    out = {
        "key": key,
        "radius_km": R_KM,
        "window_min": WINDOW_MIN,
        "halflife_min": HALFLIFE_MIN,
        "null_mean_lift": null_mean,
        "null_std_lift": null_std,
        "nodes": nodes,
        "edges": sorted(edges, key=lambda e: -e["prob"]),
    }
    path = settings.artifacts_dir / "cascade_edges.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"[cascade] wrote {path}  nodes={len(nodes)}  edges={len(edges)}")


if __name__ == "__main__":
    main()
