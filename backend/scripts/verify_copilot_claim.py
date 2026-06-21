"""Verify a co-pilot claim against the raw cleaned data.

Claim: Yelahanka @ 09:00 -> 26 incidents, avg resolution 1575 min,
       closure rate 12%, top cause vehicle_breakdown 16/26 = 62%.
"""
from __future__ import annotations

import pandas as pd

from app.core.config import settings

df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")

# Find the station name as stored
stations = sorted(s for s in df["police_station"].unique() if "yelahanka" in str(s).lower())
print("Matching station names:", stations)

sub = df[(df["police_station"].str.lower() == "yelahanka") & (df["hour"] == 9)]
print(f"\nYelahanka @ hour 09: n = {len(sub)}")

if len(sub):
    dur = pd.to_numeric(sub["duration_min"], errors="coerce")
    print(f"  avg resolution (mean duration_min) : {dur.mean():.1f} min  (n non-null={dur.notna().sum()})")
    print(f"  median duration                    : {dur.median():.1f} min")
    closure = pd.to_numeric(sub["road_closure"], errors="coerce").fillna(0)
    print(f"  road-closure rate                  : {closure.mean()*100:.1f}%  ({int(closure.sum())} of {len(sub)})")
    vc = sub["event_cause"].value_counts()
    print("  cause breakdown:")
    for cause, n in vc.items():
        print(f"    {cause:<20} {n:>3}  ({n/len(sub)*100:.0f}%)")
