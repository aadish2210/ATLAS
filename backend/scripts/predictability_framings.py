"""Honest alternative framings of 'predictability'.

The 28% is R^2 on INDIVIDUAL hourly incident counts. Individual incidents are
semi-random (Poisson), so a big chunk of the residual is irreducible noise, not
'unlearned pattern'. We compute several legitimate, more intuitive measures of
'did ATLAS learn the city's rhythm' and print them all so we can pick honest
language for the demo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import settings

df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
floored = df["start_datetime"].dt.floor("h")
actual = floored.value_counts().sort_index()
span = pd.date_range(actual.index.min(), actual.index.max(), freq="h", tz=actual.index.tz)
actual = actual.reindex(span, fill_value=0)
t = pd.DataFrame({"count": actual.values}, index=actual.index)
t["dow"] = t.index.dayofweek
t["hour"] = t.index.hour
t["date"] = t.index.date


def r2(a, p):
    a = np.asarray(a, float); p = np.asarray(p, float)
    ss_res = ((a - p) ** 2).sum(); ss_tot = ((a - a.mean()) ** 2).sum()
    return 1 - ss_res / ss_tot if ss_tot else 0.0


# 1) Current: hourly R^2
pred_hourly = t.groupby(["dow", "hour"])["count"].transform("mean").values
print(f"1) Hourly R^2 (current 'predictability')      : {r2(t['count'], pred_hourly)*100:5.1f}%")

# 2) OUT-OF-SAMPLE: learn weekday x hour profile on first 60% of dates,
#    test on the last 40%. This proves the rhythm GENERALIZES.
dates = sorted(t["date"].unique())
cut = dates[int(len(dates) * 0.6)]
train = t[t["date"] <= cut]
test = t[t["date"] > cut]
profile = train.groupby(["dow", "hour"])["count"].mean()
test_pred = test.apply(lambda r: profile.get((r["dow"], r["hour"]), train["count"].mean()), axis=1).values
print(f"2) Out-of-sample hourly R^2 (generalizes)     : {r2(test['count'], test_pred)*100:5.1f}%")

# 3) Pearson correlation between learned profile and actual (more intuitive than R^2)
r = np.corrcoef(t["count"].values, pred_hourly)[0, 1]
print(f"3) Pattern correlation (Pearson r)            : {r:.2f}  ({r*r*100:.1f}% shared variance)")

# 4) Coarser, decision-relevant blocks (6h shift blocks) where Poisson noise averages out
t["block"] = (t["hour"] // 6)
blk = t.groupby(["date", "dow", "block"])["count"].sum().reset_index()
blk_pred = blk.groupby(["dow", "block"])["count"].transform("mean").values
print(f"4) R^2 at 6-hour shift-block resolution        : {r2(blk['count'], blk_pred)*100:5.1f}%")

# 5) Daily rhythm shape: average hour-of-day curve, how well it matches
hod = t.groupby("hour")["count"].mean()
hod_pred = t["hour"].map(hod).values
print(f"5) R^2 of average hour-of-day curve            : {r2(t['count'], hod_pred)*100:5.1f}%")

# 6) Peak-window hit rate: are the busy hours correctly identified?
busy_actual = set(hod.sort_values(ascending=False).head(8).index)
# predict busy hours from the first half, check against second half busy hours
busy_train = set(train.groupby("hour")["count"].mean().sort_values(ascending=False).head(8).index)
busy_test = set(test.groupby("hour")["count"].mean().sort_values(ascending=False).head(8).index)
hit = len(busy_train & busy_test) / 8
print(f"6) Peak-hour identification (train->test)     : {hit*100:5.0f}% of top-8 busy hours match")
