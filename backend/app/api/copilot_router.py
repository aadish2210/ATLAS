"""Retrieval-grounded NL co-pilot.

NO external LLM. The pipeline:
  1. Parse the user's question with simple keyword + regex rules to extract
     entities (corridor / station / hour / day-of-week / event kind).
  2. Run the corresponding query against the parquet & artifacts.
  3. Format a templated answer with cited row counts.
  4. Refuse with a clear "insufficient history" message if the query
     resolves zero rows.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel

from app.core import data_loader as DL


router = APIRouter()


DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DOW_LOOKUP = {n.lower(): i for i, n in enumerate(DOW_NAMES)}
HOUR_RE = re.compile(r"\b(\d{1,2})\s*(am|pm)?\b", re.IGNORECASE)


class CopilotBody(BaseModel):
    query: str


def _resolve_hour(query: str) -> int | None:
    m = HOUR_RE.search(query)
    if not m:
        return None
    h = int(m.group(1))
    suf = (m.group(2) or "").lower()
    if suf == "pm" and h < 12:
        h += 12
    if suf == "am" and h == 12:
        h = 0
    if 0 <= h <= 23:
        return h
    return None


def _resolve_dow(query: str) -> int | None:
    q = query.lower()
    for name, idx in DOW_LOOKUP.items():
        if name in q:
            return idx
    if "tomorrow" in q:
        return (datetime.now().weekday() + 1) % 7
    if "today" in q:
        return datetime.now().weekday()
    return None


def _resolve_corridor(query: str) -> str | None:
    fp = DL.fingerprint().get("corridors", {})
    q = query.lower()
    for name in sorted(fp.keys(), key=lambda x: -len(x)):
        if name.lower() in q:
            return name
    # also match common Bengaluru shorthand
    aliases = {
        "silk board": "Hosur Road",
        "orr east": "ORR East 1",
        "outer ring": "ORR East 1",
        "tumkur": "Tumkur Road",
        "hosur": "Hosur Road",
        "mysore": "Mysore Road",
        "old madras": "Old Madras Road",
        "bellary": "Bellary Road 1",
    }
    for k, v in aliases.items():
        if k in q and v in fp:
            return v
    return None


def _resolve_station(query: str) -> str | None:
    stations = DL.stations().get("stations", [])
    q = query.lower()
    for s in sorted(stations, key=lambda x: -len(x["name"])):
        if s["name"].lower() in q:
            return s["name"]
    return None


def _resolve_kind(query: str) -> str | None:
    q = query.lower()
    mapping = [
        ("rally", "protest"),
        ("protest", "protest"),
        ("festival", "public_event"),
        ("match", "public_event"),
        ("cricket", "public_event"),
        ("ipl", "public_event"),
        ("vip", "vip_movement"),
        ("pm visit", "vip_movement"),
        ("procession", "procession"),
        ("construction", "construction"),
        ("breakdown", "vehicle_breakdown"),
        ("water logging", "water_logging"),
        ("flood", "water_logging"),
    ]
    for needle, val in mapping:
        if needle in q:
            return val
    return None


def _format_answer(query: str) -> dict[str, Any]:
    df = DL.events_df()
    if df.empty:
        return {"answer": "Dataset not loaded.", "citations": [], "insufficient": True}

    corridor = _resolve_corridor(query)
    station = _resolve_station(query)
    hour = _resolve_hour(query)
    dow = _resolve_dow(query)
    kind = _resolve_kind(query)

    mask = pd.Series(True, index=df.index)
    if corridor:
        mask &= df["corridor"] == corridor
    if station:
        mask &= df["police_station"] == station
    if hour is not None:
        mask &= df["hour"] == hour
    if dow is not None:
        mask &= df["dow"] == dow
    if kind:
        mask &= df["event_cause"] == kind

    sub = df.loc[mask]
    n = int(len(sub))

    citations = [
        {"type": "row_count", "value": n, "where": {
            "corridor": corridor, "station": station, "hour": hour,
            "day_of_week": DOW_NAMES[dow] if dow is not None else None,
            "event_cause": kind,
        }}
    ]

    if n == 0:
        return {
            "answer": (
                "Insufficient history to answer that confidently. "
                "I have no events in the dataset matching those filters."
            ),
            "citations": citations,
            "insufficient": True,
        }

    # Durations in civic ticket data are heavily right-skewed: a few tickets are
    # left open for days, which makes the MEAN nonsensical (e.g. "1575 min").
    # We report the MEDIAN (typical case) and how many incidents actually had a
    # recorded resolution time, so the number is both honest and sensible.
    dur_series = pd.to_numeric(sub["duration_min"], errors="coerce").dropna()
    med_dur = float(dur_series.median()) if not dur_series.empty else None
    n_with_duration = int(dur_series.shape[0])
    closure_pct = float(sub["road_closure"].mean()) * 100
    cause_top = sub["event_cause"].value_counts().head(3).to_dict()

    fp = DL.fingerprint().get("corridors", {}).get(corridor, {}) if corridor else {}
    predict = fp.get("predictability")

    # build prediction-style answer
    parts = [f"Based on **{n} historical incidents**"]
    locators = []
    if corridor: locators.append(f"on {corridor}")
    if station: locators.append(f"handled by {station}")
    if dow is not None: locators.append(f"on {DOW_NAMES[dow]}s")
    if hour is not None: locators.append(f"at {hour:02d}:00")
    if locators: parts.append(" ".join(locators))
    parts.append(":")
    bullets: list[str] = []
    if med_dur is not None:
        bullets.append(
            f"typical (median) resolution **{med_dur:.0f} min** "
            f"(from {n_with_duration} with recorded close times)"
        )
    bullets.append(f"road-closure rate **{closure_pct:.0f}%**")
    if cause_top:
        top_cause = next(iter(cause_top))
        bullets.append(
            f"top cause **{top_cause}** ({cause_top[top_cause]} of {n} = "
            f"{100*cause_top[top_cause]/n:.0f}%)"
        )
    if predict is not None:
        bullets.append(f"corridor predictability **{predict*100:.0f}%**")

    # nearest fast-responding station
    if not sub.empty and station is None:
        sample = sub.iloc[0]
        ns = DL.nearest_station(float(sample["latitude"]), float(sample["longitude"]))
        if ns and ns.get("median_response_min") is not None:
            bullets.append(
                f"closest fast-responder **{ns['name']}** (median response "
                f"{ns['median_response_min']:.0f} min)"
            )

    answer = parts[0]
    if len(parts) > 1:
        answer += " " + " ".join(parts[1:-1]) + parts[-1]
    answer += " " + "; ".join(bullets) + "."

    citations += [
        {"type": "stat", "field": "duration_min_median", "value": round(med_dur or 0, 1)},
        {"type": "stat", "field": "n_with_recorded_duration", "value": n_with_duration},
        {"type": "stat", "field": "road_closure_pct", "value": round(closure_pct, 1)},
        {"type": "top_cause", "value": cause_top},
    ]
    return {"answer": answer, "citations": citations, "insufficient": False,
            "filters": {"corridor": corridor, "station": station,
                        "hour": hour, "dow": dow, "kind": kind}}


@router.post("/copilot/query")
def copilot(body: CopilotBody) -> dict:
    return _format_answer(body.query)
