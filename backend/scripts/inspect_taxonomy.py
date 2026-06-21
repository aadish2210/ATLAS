"""Audit the dataset's event taxonomy and the simulator's planning kinds.

Two questions to answer with hard data:
  1. What does `event_type` actually contain? Why isn't 'vehicle_breakdown' there?
  2. What does `event_cause` contain, and how does that map to the simulator's
     dropdown of planning kinds (sports_match, rally, festival, etc.)?
"""
from __future__ import annotations

import pandas as pd

from app.core.config import settings


def main() -> None:
    df = pd.read_csv(settings.raw_csv_path, low_memory=False)
    print(f"raw rows = {len(df):,}\n")

    print("=== event_type (the column the user expected to find breakdowns under) ===")
    et = df["event_type"].fillna("__MISSING__").value_counts()
    for k, v in et.items():
        print(f"  {k:<20}  {v:>5}  ({v/len(df)*100:.1f}%)")

    print("\n=== event_cause (the column that holds the actual incident kind) ===")
    ec = df["event_cause"].fillna("__MISSING__").value_counts()
    for k, v in ec.items():
        print(f"  {k:<22}  {v:>5}  ({v/len(df)*100:.1f}%)")

    print("\n=== cross-tab event_type x event_cause ===")
    ct = pd.crosstab(df["event_type"].fillna("__M__"), df["event_cause"].fillna("__M__"))
    print(ct.to_string())

    print("\n=== simulator dropdown kinds and their support in the data ===")
    # mirrors backend/app/models/simulator.py CAUSE_TO_DATASET
    mapping = {
        "rally": "protest",
        "festival": "public_event",
        "sports_match": "public_event",
        "vip_movement": "vip_movement",
        "procession": "procession",
        "construction": "construction",
        "protest": "protest",
    }
    for ui_kind, ds_cause in mapping.items():
        n = int((df["event_cause"] == ds_cause).sum())
        print(f"  UI dropdown '{ui_kind}' -> dataset cause '{ds_cause}'  rows={n}")


if __name__ == "__main__":
    main()
