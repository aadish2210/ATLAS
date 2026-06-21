"""Step 2 — Behavioral Fingerprint Engine.

Mines the city's recurring rhythm from incident timestamps:
  * Per-corridor 24x7 hour-of-day x day-of-week heatmap
  * Predictability Score = 1 - normalized residual variance after removing
    the hour x dow seasonal mean
  * Anomaly days = dates with daily count z-score > 3.5 using MAD
  * Drainage Vulnerability Index per zone (% weather-flagged events)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402

MIN_CORRIDOR_EVENTS = 30


def _predictability(events: pd.DataFrame) -> float:
    """How much of the city's hourly incident rhythm is explained by a recurring
    (day-of-week x hour) seasonal pattern. Returns R^2 in [0, 1].

    Higher = more predictable / regular. We compare each hour's actual incident
    count against the average count for that same weekday+hour slot.
    """
    daily = events.groupby("date").size()
    if len(daily) < 14:
        return 0.0

    # Actual incidents per clock-hour, kept timezone-aware so the hourly grid
    # lines up with the data (a tz-naive grid silently zeroes everything).
    floored = events["start_datetime"].dt.floor("h")
    actual = floored.value_counts().sort_index()
    if actual.empty:
        return 0.0
    span = pd.date_range(actual.index.min(), actual.index.max(),
                         freq="h", tz=actual.index.tz)
    actual = actual.reindex(span, fill_value=0)
    if len(actual) < 24 or actual.var() == 0:
        return 0.0

    # Expected = MEAN count for each (dow, hour) slot, aligned to every hour.
    tmp = pd.DataFrame({"count": actual.values}, index=actual.index)
    tmp["dow"] = tmp.index.dayofweek
    tmp["hour"] = tmp.index.hour
    pred = tmp.groupby(["dow", "hour"])["count"].transform("mean").values

    a = actual.values.astype(float)
    ss_res = float(((a - pred) ** 2).sum())
    ss_tot = float(((a - a.mean()) ** 2).sum())
    if ss_tot == 0:
        return 0.0
    r2 = 1.0 - ss_res / ss_tot
    return float(np.clip(r2, 0.0, 1.0))


def _anomaly_days(events: pd.DataFrame, k: float = 3.5) -> list[dict]:
    daily = events.groupby("date").size()
    if len(daily) < 7:
        return []
    median = daily.median()
    mad = np.median(np.abs(daily - median)) or 1.0
    z = 0.6745 * (daily - median) / mad
    spikes = z[z > k].sort_values(ascending=False)
    return [
        {"date": str(d), "count": int(daily.loc[d]), "z": round(float(z.loc[d]), 2)}
        for d in spikes.index[:25]
    ]


def _hour_dow_heatmap(events: pd.DataFrame) -> list[list[float]]:
    grid = (
        events.groupby(["dow", "hour"]).size()
        .unstack(fill_value=0)
        .reindex(index=range(7), columns=range(24), fill_value=0)
    )
    if grid.values.max() == 0:
        return grid.values.astype(float).tolist()
    return (grid.values / grid.values.max()).round(3).tolist()


def _breathing_24h(events: pd.DataFrame) -> list[float]:
    by_hour = events.groupby("hour").size().reindex(range(24), fill_value=0)
    if by_hour.max() == 0:
        return [0.0] * 24
    return (by_hour.values / by_hour.max()).round(3).tolist()


def main() -> None:
    df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
    print(f"[fingerprint] {len(df):,} events")

    by_corridor = df.groupby("corridor")
    corridor_out: dict[str, dict] = {}
    for name, group in by_corridor:
        if name in {"Unknown", "Non-corridor"} or len(group) < MIN_CORRIDOR_EVENTS:
            continue
        corridor_out[name] = {
            "events": int(len(group)),
            "predictability": round(_predictability(group), 3),
            "anomaly_days": _anomaly_days(group),
            "heatmap": _hour_dow_heatmap(group),
            "breathing": _breathing_24h(group),
            "lat_centroid": float(group["latitude"].mean()),
            "lng_centroid": float(group["longitude"].mean()),
            "weather_share": round(float(group["weather_flag"].mean()), 3),
            "closure_share": round(float(group["road_closure"].mean()), 3),
        }

    # --- city-wide ---
    city = {
        "events": int(len(df)),
        "date_min": str(df["start_datetime"].min().date()),
        "date_max": str(df["start_datetime"].max().date()),
        "predictability": round(_predictability(df), 3),
        "anomaly_days": _anomaly_days(df),
        "heatmap": _hour_dow_heatmap(df),
        "breathing": _breathing_24h(df),
    }

    # --- Drainage Vulnerability Index per zone ---
    dvi: dict[str, dict] = {}
    for zone, group in df.groupby("zone"):
        if zone == "Unknown" or len(group) < 20:
            continue
        share = float(group["weather_flag"].mean())
        dvi[zone] = {
            "events": int(len(group)),
            "weather_share": round(share, 3),
            "category": "Critical" if share >= 0.20 else "Moderate" if share >= 0.10 else "Resilient",
            "lat_centroid": float(group["latitude"].mean()),
            "lng_centroid": float(group["longitude"].mean()),
        }

    payload = {
        "city": city,
        "corridors": corridor_out,
        "dvi": dvi,
        "n_corridors": len(corridor_out),
    }

    out = settings.artifacts_dir / "fingerprint.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"[fingerprint] wrote {out}  corridors={len(corridor_out)}  zones={len(dvi)}")


if __name__ == "__main__":
    main()
