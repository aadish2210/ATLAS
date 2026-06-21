"""Step 5 — Police station performance profiles.

For each police_station compute:
  * coverage centroid (mean of incident locations handled)
  * avg / median response_min  (response_min = created_date - start_datetime)
  * avg / median resolution duration
  * hourly load profile (events handled per hour-of-day)
  * top causes
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402


def main() -> None:
    df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
    df = df[df["police_station"] != "Unknown"].copy()
    print(f"[stations] events with station: {len(df):,}")

    rows = []
    for name, g in df.groupby("police_station"):
        if len(g) < settings.station_min_events:
            continue
        hourly = g.groupby("hour").size().reindex(range(24), fill_value=0)
        load = (hourly / max(hourly.max(), 1)).round(3).tolist()
        causes = (g["event_cause"].value_counts().head(5)
                  .to_dict())
        rows.append({
            "name": name,
            "lat": float(g["latitude"].mean()),
            "lng": float(g["longitude"].mean()),
            "events": int(len(g)),
            "avg_response_min": float(np.nanmean(g["response_min"]))
                if g["response_min"].notna().any() else None,
            "median_response_min": float(np.nanmedian(g["response_min"]))
                if g["response_min"].notna().any() else None,
            "avg_resolution_min": float(np.nanmean(g["duration_min"]))
                if g["duration_min"].notna().any() else None,
            "median_resolution_min": float(np.nanmedian(g["duration_min"]))
                if g["duration_min"].notna().any() else None,
            "hourly_load": load,
            "top_causes": causes,
            "lat_p10": float(np.percentile(g["latitude"], 10)),
            "lat_p90": float(np.percentile(g["latitude"], 90)),
            "lng_p10": float(np.percentile(g["longitude"], 10)),
            "lng_p90": float(np.percentile(g["longitude"], 90)),
        })
    rows.sort(key=lambda r: -r["events"])

    out = {"stations": rows, "n": len(rows)}
    (settings.artifacts_dir / "stations.json").write_text(json.dumps(out, indent=2))
    print(f"[stations] wrote {len(rows)} stations")


if __name__ == "__main__":
    main()
