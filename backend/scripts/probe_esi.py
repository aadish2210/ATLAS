"""One-shot probe to verify the ESI formula behaves as documented.

Prints the inputs that should, by the formula, drive ESI to its maximum
given the *current* artifacts. Throwaway — safe to delete.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

CAL = json.loads(Path("artifacts/esi_calibration.json").read_text())
DF = pd.read_parquet("artifacts/events_clean.parquet")

top_corr = sorted(CAL["corridor_volume"].items(), key=lambda x: -x[1])[:5]
print("TOP corridors by historical volume (drives corridor_norm):")
for name, vol in top_corr:
    print(f"  {name:<25} vol={vol:<4} norm={vol / CAL['corridor_volume_max']:.2f}")

top_cas = sorted(CAL["cascade_count_by_zone"].items(), key=lambda x: -x[1])[:5]
print("\nTOP keys in cascade_count_by_zone (these are POLICE STATIONS, not zones):")
for name, vol in top_cas:
    print(f"  {name:<25} count={vol:<3} norm={vol / CAL['cascade_count_max']:.2f}")

print("\nMedian duration_min by event_cause (top 10 longest):")
agg = (
    DF.groupby("event_cause")["duration_min"]
    .agg(["median", "count"])
    .sort_values("median", ascending=False)
    .head(10)
)
print(agg.to_string())

best_corr = top_corr[0][0]
sample = (
    DF[DF["corridor"] == best_corr][
        ["latitude", "longitude", "zone", "police_station"]
    ]
    .dropna()
    .iloc[0]
)
print(
    f"\nSample point on {best_corr}: "
    f"lat={sample.latitude:.4f} lng={sample.longitude:.4f} "
    f"zone={sample.zone} station={sample.police_station}"
)
print(
    f"\nduration_p10={CAL['duration_p10']:.1f}  duration_p90={CAL['duration_p90']:.1f}"
)
