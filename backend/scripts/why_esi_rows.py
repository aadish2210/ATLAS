"""Explain why ESI training set is only ~2,380 of 8,041 rows."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import settings

df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
print(f"Total cleaned rows                      : {len(df):,}")

dur = pd.to_numeric(df["duration_min"], errors="coerce")
print(f"  rows with NO duration (never closed)  : {dur.isna().sum():,}  ({dur.isna().mean()*100:.0f}%)")

have = df[dur.notna()]
d = dur.dropna()
print(f"  rows WITH a duration                  : {len(d):,}")
print(f"    of those, <= 0 min (bad timestamps) : {(d <= 0).sum():,}")
print(f"    of those, > 12 h  (unclosed tickets): {(d > 720).sum():,}")
kept = d[(d > 0) & (d < 720)]
print(f"  => usable for ESI (0 < dur < 12h)     : {len(kept):,}")
print()
print(f"median of the kept durations            : {kept.median():.0f} min")
print(f"median of ALL recorded durations        : {d.median():.0f} min")
print(f"mean   of ALL recorded durations        : {d.mean():.0f} min  <- skewed by unclosed tickets")
