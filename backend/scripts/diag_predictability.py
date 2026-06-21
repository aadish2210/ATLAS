"""Diagnose why city predictability = 0."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import settings

df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
df["date"] = df["start_datetime"].dt.date.astype(str)

# how many weeks of data?
span = pd.date_range(df["start_datetime"].min(), df["start_datetime"].max(), freq="h")
n_weeks = len(span) / (24 * 7)
print(f"date range hours = {len(span)}  (~{n_weeks:.1f} weeks)")

# seasonal bucket = TOTAL count per (dow,hour) across ALL weeks
seasonal = df.groupby(["dow", "hour"]).size().rename("count").reset_index()
print("seasonal bucket count stats (summed over all weeks):")
print(f"  mean per (dow,hour) bucket = {seasonal['count'].mean():.1f}")

# actual = count in a SINGLE hour slot
actual = df.groupby(df["start_datetime"].dt.floor("h")).size().reindex(span, fill_value=0)
print(f"actual per-single-hour count: mean = {actual.mean():.2f}  max = {actual.max()}")

print()
print("THE MISMATCH:")
print(f"  expected/pred values are ~{seasonal['count'].mean():.0f} per slot")
print(f"  actual values are ~{actual.mean():.2f} per slot")
print("  -> pred is inflated ~", round(seasonal['count'].mean()/max(actual.mean(),1e-9)), "x, so R^2 goes very negative and clips to 0.")

# --- CORRECT computation: tz-aware span + per-slot MEAN ---
floored = df["start_datetime"].dt.floor("h")
actual2 = floored.value_counts().sort_index()
span2 = pd.date_range(actual2.index.min(), actual2.index.max(), freq="h", tz=actual2.index.tz)
actual2 = actual2.reindex(span2, fill_value=0)
tmp = pd.DataFrame({"count": actual2.values}, index=actual2.index)
tmp["dow"] = tmp.index.dayofweek
tmp["hour"] = tmp.index.hour
pred2 = tmp.groupby(["dow", "hour"])["count"].transform("mean").values
a2 = actual2.values
r2_fixed = 1 - ((a2 - pred2) ** 2).sum() / ((a2 - a2.mean()) ** 2).sum()
print()
print(f"actual2 (tz-aware) mean = {a2.mean():.2f}  max = {a2.max()}  (should be > 0 now)")
print(f"Predictability with the CORRECT method: R^2 = {r2_fixed:.3f}")
