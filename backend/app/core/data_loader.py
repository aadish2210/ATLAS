"""Singleton-style loader. Reads all artifacts once at import time."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from .config import settings


def _read_json(name: str) -> dict[str, Any]:
    path = settings.artifacts_dir / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def fingerprint() -> dict[str, Any]:
    return _read_json("fingerprint.json")


@lru_cache(maxsize=1)
def cascade() -> dict[str, Any]:
    return _read_json("cascade_edges.json")


@lru_cache(maxsize=1)
def stations() -> dict[str, Any]:
    return _read_json("stations.json")


@lru_cache(maxsize=1)
def audit() -> dict[str, Any]:
    return _read_json("audit.json")


@lru_cache(maxsize=1)
def corridor_state() -> dict[str, Any]:
    return _read_json("corridor_state.json")


@lru_cache(maxsize=1)
def corridors_geojson() -> dict[str, Any]:
    path = settings.artifacts_dir / "corridors.geojson"
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def esi_calibration() -> dict[str, Any]:
    return _read_json("esi_calibration.json")


@lru_cache(maxsize=1)
def validation_report() -> dict[str, Any]:
    return _read_json("validation_report.json")


@lru_cache(maxsize=1)
def backtest() -> dict[str, Any]:
    return _read_json("backtest.json")


@lru_cache(maxsize=1)
def semantic() -> dict[str, Any]:
    return _read_json("semantic.json")


@lru_cache(maxsize=1)
def severity_profile() -> dict[str, Any]:
    return _read_json("severity_profile.json")


@lru_cache(maxsize=1)
def esi_model():
    path = settings.artifacts_dir / "esi_model.pkl"
    if not path.exists():
        return None
    return joblib.load(path)


@lru_cache(maxsize=1)
def esi_quantile_low():
    path = settings.artifacts_dir / "esi_q05.pkl"
    if not path.exists():
        return None
    return joblib.load(path)


@lru_cache(maxsize=1)
def esi_quantile_high():
    path = settings.artifacts_dir / "esi_q95.pkl"
    if not path.exists():
        return None
    return joblib.load(path)


@lru_cache(maxsize=1)
def events_df() -> pd.DataFrame:
    path = settings.artifacts_dir / "events_clean.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


# ---------------------------------------------------------------------------
# Helpers used by the simulator and copilot endpoints

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest_station(lat: float, lng: float) -> dict[str, Any] | None:
    s = stations().get("stations", [])
    if not s:
        return None
    best = min(s, key=lambda r: haversine_km(lat, lng, r["lat"], r["lng"]))
    return best


def nearest_corridor(lat: float, lng: float) -> str | None:
    geo = corridors_geojson()
    best, best_d = None, float("inf")
    for feat in geo.get("features", []):
        coords = feat["geometry"]["coordinates"]
        for lng2, lat2 in coords:
            d = haversine_km(lat, lng, lat2, lng2)
            if d < best_d:
                best_d, best = d, feat["properties"]["name"]
    return best


def all_loaded() -> dict[str, bool]:
    return {
        "fingerprint": bool(fingerprint()),
        "cascade": bool(cascade()),
        "stations": bool(stations().get("stations")),
        "audit": bool(audit()),
        "corridors": bool(corridors_geojson().get("features")),
        "esi_model": esi_model() is not None,
        "validation": bool(validation_report()),
        "backtest": bool(backtest()),
        "semantic": bool(semantic()),
        "severity": bool(severity_profile()),
    }


def replay_timeline(date: str) -> dict[str, Any]:
    """Return the ordered incident timeline for one day plus the cascade edges
    that connect consecutive incidents — feeds the front-end time-lapse."""
    df = events_df()
    if df.empty:
        return {"date": date, "events": [], "edges": []}
    d = df.copy()
    d = d[d["start_datetime"].notna()]
    d["date"] = d["start_datetime"].dt.date.astype(str)
    day = d[d["date"] == date].sort_values("start_datetime")
    if day.empty:
        return {"date": date, "events": [], "edges": []}

    events = []
    for _, r in day.iterrows():
        ts = r["start_datetime"]
        events.append({
            "id": str(r.get("id", "")),
            "t": ts.isoformat(),
            "minute": int(ts.hour * 60 + ts.minute),
            "hour": int(ts.hour),
            "lat": float(r["latitude"]),
            "lng": float(r["longitude"]),
            "station": str(r.get("police_station", "Unknown")),
            "cause": str(r.get("event_cause", "unknown")),
            "duration_min": (None if pd.isna(r.get("duration_min")) else float(r["duration_min"])),
        })

    # cascade edges among stations active this day (for "predicted-before-it-happened")
    cas = cascade()
    node_pos = {n["id"]: (n["lat"], n["lng"]) for n in cas.get("nodes", [])}
    active = set(day["police_station"])
    edges = []
    for e in cas.get("edges", []):
        if e["from"] in active and e["to"] in active and e.get("prob", 0) >= 0.15:
            if e["from"] in node_pos and e["to"] in node_pos:
                fa = node_pos[e["from"]]
                ta = node_pos[e["to"]]
                edges.append({
                    "from": e["from"], "to": e["to"],
                    "from_lat": fa[0], "from_lng": fa[1],
                    "to_lat": ta[0], "to_lng": ta[1],
                    "prob": e["prob"], "delay_min": e.get("delay_min", 0),
                })
    return {"date": date, "events": events, "edges": edges,
            "n_events": len(events), "n_edges": len(edges)}
