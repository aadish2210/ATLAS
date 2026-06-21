"""Step 1 — Clean the raw Astram CSV into a typed parquet.

Run: ``python -m pipeline.01_clean`` (from ``backend/``)
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402


WEATHER_KEYWORDS = re.compile(
    r"water|rain|flood|drainage|chamber|leak|wet|monsoon|slip|skid|pothole|logging",
    re.IGNORECASE,
)
EVENT_KEYWORDS = re.compile(
    r"rally|procession|festival|temple|match|cricket|ipl|rcb|pm visit|vip|protest|"
    r"bandh|jatra|utsav|uthsava|mela|fair|parade|jaathra|jathra|brahma",
    re.IGNORECASE,
)

# Indian commercial truck plates roughly follow: 2 letters + 1-2 digits + 1-2 letters + 4 digits.
COMMERCIAL_VEH_RE = re.compile(r"^[A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,2}\s?\d{3,4}$", re.IGNORECASE)
ANONYMIZED_VEH_RE = re.compile(r"^FKN\d{2}[A-Z]{2}\d{4}$", re.IGNORECASE)

CARGO_BUCKETS = {
    "goods": "goods",
    "construction": "construction",
    "electric": "utility",
    "utility": "utility",
    "bbmp": "utility",
    "fuel": "hazmat",
    "gas": "hazmat",
    "chemical": "hazmat",
    "passenger": "passenger",
    "people": "passenger",
}


def _cargo_bucket(value) -> str:
    if value is None:
        return "Unknown"
    if isinstance(value, float) and math.isnan(value):
        return "Unknown"
    v = str(value).lower()
    if not v or v in {"nan", "none"}:
        return "Unknown"
    for k, label in CARGO_BUCKETS.items():
        if k in v:
            return label
    if v != "unknown":
        return "other"
    return "Unknown"


def _desc_len_bucket(text) -> str:
    if text is None:
        return "none"
    if isinstance(text, float) and math.isnan(text):
        return "none"
    n = len(str(text))
    if n < 1:
        return "none"
    if n < 60:
        return "short"
    if n < 200:
        return "medium"
    return "long"


def _count_route_points(raw) -> int:
    if not isinstance(raw, str) or len(raw) < 4:
        return 0
    return max(0, raw.count("[") - 1)


def _to_dt(series: pd.Series) -> pd.Series:
    out = pd.to_datetime(series, errors="coerce", utc=True)
    return out.dt.tz_convert(settings.bengaluru_tz)


def _safe_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def clean(raw_path: Path = settings.raw_csv_path) -> pd.DataFrame:
    print(f"[clean] reading {raw_path}")
    df = pd.read_csv(raw_path, low_memory=False, na_values=["NULL", "null", ""])
    print(f"[clean] raw rows: {len(df):,}")

    # ---- timestamps -------------------------------------------------------
    df["start_datetime"] = _to_dt(df["start_datetime"])
    df["end_datetime"] = _to_dt(df["end_datetime"])
    df["closed_datetime"] = _to_dt(df["closed_datetime"])
    df["resolved_datetime"] = _to_dt(df["resolved_datetime"])
    df["created_date"] = _to_dt(df["created_date"])
    df["modified_datetime"] = _to_dt(df["modified_datetime"])

    df = df.dropna(subset=["start_datetime"]).copy()

    # ---- coords -----------------------------------------------------------
    for col in ["latitude", "longitude", "endlatitude", "endlongitude",
                "resolved_at_latitude", "resolved_at_longitude"]:
        if col in df:
            df[col] = _safe_float(df[col])

    in_bbox = (
        (df["latitude"].between(settings.bbox_lat_min, settings.bbox_lat_max))
        & (df["longitude"].between(settings.bbox_lng_min, settings.bbox_lng_max))
    )
    df = df.loc[in_bbox].copy()
    print(f"[clean] after bbox filter: {len(df):,}")

    # ---- derived features -------------------------------------------------
    df["duration_min"] = (
        (df["closed_datetime"] - df["start_datetime"]).dt.total_seconds() / 60
    )
    df["planned_duration_min"] = (
        (df["end_datetime"] - df["start_datetime"]).dt.total_seconds() / 60
    )
    df["response_min"] = (
        (df["created_date"] - df["start_datetime"]).dt.total_seconds() / 60
    ).abs()

    # cap junk (some closed_datetime predates start_datetime)
    df.loc[df["duration_min"] < 0, "duration_min"] = np.nan
    df.loc[df["duration_min"] > 60 * 24 * 14, "duration_min"] = np.nan
    df.loc[df["planned_duration_min"] < 0, "planned_duration_min"] = np.nan
    df.loc[df["response_min"] > 240, "response_min"] = np.nan

    df["hour"] = df["start_datetime"].dt.hour
    df["dow"] = df["start_datetime"].dt.dayofweek
    df["date"] = df["start_datetime"].dt.date.astype(str)
    df["month"] = df["start_datetime"].dt.month
    df["is_weekend"] = df["dow"].isin([5, 6]).astype(int)

    # ---- text flags -------------------------------------------------------
    descr = df["description"].fillna("").astype(str)
    cause = df["event_cause"].fillna("").astype(str)
    df["weather_flag"] = (
        descr.str.contains(WEATHER_KEYWORDS, regex=True)
        | cause.str.contains(WEATHER_KEYWORDS, regex=True)
    ).astype(int)
    df["event_kw_flag"] = (
        descr.str.contains(EVENT_KEYWORDS, regex=True)
        | cause.str.contains(EVENT_KEYWORDS, regex=True)
    ).astype(int)

    df["is_event_driven"] = (
        df["event_cause"].isin(settings.event_driven_causes)
        | (df["event_type"] == "planned")
        | (df["event_kw_flag"] == 1)
    ).astype(int)

    df["desc_len_bucket"] = descr.map(_desc_len_bucket)

    # ---- vehicle features (veh_no/cargo_material/age_of_truck/direction) ---
    if "veh_no" in df.columns:
        veh_no = df["veh_no"].astype(str).str.strip()
        veh_no = veh_no.replace({"nan": "", "NaN": "", "None": ""})
    else:
        veh_no = pd.Series([""] * len(df), index=df.index)
    df["has_veh_no"] = veh_no.str.len().gt(0).astype(int)
    commercial = veh_no.str.match(COMMERCIAL_VEH_RE, na=False)
    anonymized = veh_no.str.match(ANONYMIZED_VEH_RE, na=False)
    df["is_commercial_veh"] = (commercial | anonymized).astype(int)

    if "cargo_material" in df.columns:
        df["cargo_type"] = df["cargo_material"].astype(str).map(_cargo_bucket).fillna("Unknown")
    else:
        df["cargo_type"] = "Unknown"
    df["has_cargo"] = (df["cargo_type"] != "Unknown").astype(int)

    if "age_of_truck" in df.columns:
        truck_age = pd.to_numeric(df["age_of_truck"], errors="coerce")
    else:
        truck_age = pd.Series([np.nan] * len(df), index=df.index)
    df["truck_age"] = truck_age.fillna(0).clip(lower=0, upper=40).astype(float)

    if "direction" in df.columns:
        direction = df["direction"].astype(str).str.lower().str.strip()
        df["direction"] = direction.where(
            direction.notna() & (direction != "nan") & (direction != ""), "Unknown"
        )
    else:
        df["direction"] = "Unknown"

    # ---- ops/workflow proxies --------------------------------------------
    created_by = df.get("created_by_id")
    modified_by = df.get("last_modified_by_id")
    closed_by = df.get("closed_by_id")
    assigned_to = df.get("assigned_to_police_id")

    if created_by is not None and modified_by is not None:
        df["was_reassigned"] = (
            modified_by.notna()
            & created_by.notna()
            & (modified_by.astype(str) != created_by.astype(str))
        ).astype(int)
    else:
        df["was_reassigned"] = 0

    df["has_assigned_officer"] = (
        assigned_to.notna().astype(int) if assigned_to is not None else 0
    )
    if closed_by is not None and created_by is not None:
        df["has_distinct_closer"] = (
            closed_by.notna() & (closed_by.astype(str) != created_by.astype(str))
        ).astype(int)
    else:
        df["has_distinct_closer"] = 0
    df["has_kgid"] = df["kgid"].notna().astype(int) if "kgid" in df.columns else 0

    # ---- spatial extras ---------------------------------------------------
    if "end_address" in df.columns:
        df["has_end_address"] = df["end_address"].notna().astype(int)
    else:
        df["has_end_address"] = 0

    if "route_path" in df.columns:
        route_points = df["route_path"].map(_count_route_points)
    else:
        route_points = pd.Series([0] * len(df), index=df.index)
    df["route_points"] = route_points.clip(lower=0, upper=200).astype(int)
    df["has_route_path"] = (df["route_points"] > 0).astype(int)

    if "gba_identifier" in df.columns:
        df["gba_identifier"] = (
            df["gba_identifier"].fillna("Unknown").astype(str).str.strip()
        )
    else:
        df["gba_identifier"] = "Unknown"

    # ---- categorical hygiene ---------------------------------------------
    for col in ["corridor", "zone", "police_station", "priority", "veh_type",
                "event_cause", "event_type", "status"]:
        if col in df:
            df[col] = df[col].fillna("Unknown").astype(str).str.strip()
            df.loc[df[col].isin(["nan", "NaN", "NULL", ""]), col] = "Unknown"

    df["road_closure"] = (
        df["requires_road_closure"].astype(str).str.upper().eq("TRUE")
    ).astype(int)
    df["priority_high"] = df["priority"].str.lower().eq("high").astype(int)

    keep_cols = [
        "id", "event_type", "event_cause", "is_event_driven",
        "latitude", "longitude", "endlatitude", "endlongitude",
        "address", "start_datetime", "end_datetime", "closed_datetime",
        "resolved_datetime", "created_date", "modified_datetime",
        "duration_min", "planned_duration_min", "response_min",
        "hour", "dow", "date", "month", "is_weekend",
        "corridor", "zone", "police_station",
        "priority", "priority_high", "road_closure",
        "weather_flag", "event_kw_flag",
        "veh_type", "description", "junction", "status",
        "desc_len_bucket", "direction", "gba_identifier",
        "has_veh_no", "is_commercial_veh",
        "cargo_type", "has_cargo", "truck_age",
        "was_reassigned", "has_assigned_officer", "has_distinct_closer", "has_kgid",
        "has_end_address", "has_route_path", "route_points",
    ]
    keep_cols = [c for c in keep_cols if c in df.columns]
    out = df[keep_cols].reset_index(drop=True)

    print(f"[clean] final rows: {len(out):,}  cols: {len(out.columns)}")
    return out


def main() -> None:
    df = clean()
    out_path = settings.artifacts_dir / "events_clean.parquet"
    df.to_parquet(out_path, index=False)
    print(f"[clean] wrote {out_path}  ({out_path.stat().st_size/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
