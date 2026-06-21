"""Event simulator — wires precomputed artifacts into a forecast for a
hypothetical event dropped anywhere on the map.

Returns:
  * predicted ESI with 90% conformal interval
  * cascade ripple — secondary events with location + time + probability
  * recommended deployment — stations + officer counts + ETA
  * barricades — pin coordinates near anticipated closure points
  * diversions — alternate corridor names with predicted residual load
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
    _IST = ZoneInfo("Asia/Kolkata")
except Exception:
    _IST = None

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from app.core import data_loader as DL
from app.core.config import settings


# ---- Cause taxonomy (keep in sync with frontend dropdown) ------------------
CAUSE_TO_DATASET = {
    "rally": "protest",
    "festival": "public_event",
    "sports_match": "public_event",
    "vip_movement": "vip_movement",
    "procession": "procession",
    "construction": "construction",
    "protest": "protest",
}

# Planning events with a known operational footprint. For these we trust the
# planner's duration_min and apply a kind-specific severity floor, because the
# raw dataset is dominated by short vehicle breakdowns and the GBM has no way
# to infer that an IPL match runs ~5h with road closure.
PLANNED_KINDS = {
    "rally", "festival", "sports_match", "vip_movement",
    "procession", "construction", "protest",
}

KIND_PRIOR_MIN_DURATION = {
    "rally": 180,
    "festival": 300,
    "sports_match": 300,
    "vip_movement": 60,
    "procession": 150,
    "construction": 480,
    "protest": 180,
}

KIND_SEVERITY_BASE = {
    "rally": 5.0,
    "festival": 5.5,
    "sports_match": 5.5,
    "vip_movement": 6.0,
    "procession": 4.0,
    "construction": 3.0,
    "protest": 5.5,
}

DEFAULT_FEATURE_DEFAULTS = {
    "veh_type": "Unknown",
    "is_event_driven": 1,
}


@dataclass
class SimRequest:
    lat: float
    lng: float
    event_kind: str         # rally / festival / sports_match / vip_movement / procession / construction / protest
    expected_size: str      # small / medium / large
    duration_min: int = 60  # user-chosen expected duration
    requires_road_closure: bool = False
    when_iso: str | None = None  # planning timestamp; defaults to "now"


# ----- ESI ------------------------------------------------------------------

def _esi_inputs(req: SimRequest, corridor: str | None, zone: str | None,
                hour: int, dow: int, month: int) -> pd.DataFrame:
    cause = CAUSE_TO_DATASET.get(req.event_kind, "public_event")
    is_large_or_closure = req.requires_road_closure or req.expected_size == "large"
    row = {
        # baseline features
        "event_cause": cause,
        "corridor": corridor or "Unknown",
        "zone": zone or "Unknown",
        "priority": "High" if is_large_or_closure else "Low",
        "veh_type": "Unknown",
        "hour": hour,
        "dow": dow,
        "is_weekend": int(dow in (5, 6)),
        "road_closure": int(req.requires_road_closure),
        "weather_flag": 0,
        "event_kw_flag": 1,
        "is_event_driven": 1,
        "month": month,
        "priority_high": 1 if is_large_or_closure else 0,
        # extended features (sensible planning defaults)
        "direction": "Unknown",
        "gba_identifier": "Unknown",
        "cargo_type": "Unknown",
        "desc_len_bucket": "medium",
        "has_veh_no": 0,
        "is_commercial_veh": 0,
        "has_cargo": 0,
        "truck_age": 0.0,
        "was_reassigned": 0,
        "has_assigned_officer": 1,        # planned event => an officer is pre-assigned
        "has_distinct_closer": 0,
        "has_kgid": 0,
        "has_end_address": 0,
        "has_route_path": 0,
        "route_points": 0,
    }
    return pd.DataFrame([row])


def _esi_score(req: SimRequest, corridor: str | None, zone: str | None,
               hour: int, dow: int, month: int,
               seed_station: str | None) -> dict[str, Any]:
    model = DL.esi_model()
    cal = DL.esi_calibration()
    if model is None or not cal:
        # heuristic fallback
        base = 5.0
        score = base + (2 if req.requires_road_closure else 0) + (1 if req.expected_size == "large" else 0)
        return {"esi": min(10.0, score), "low": max(0, score - 2),
                "high": min(10, score + 2), "duration_min": req.duration_min}

    feats = _esi_inputs(req, corridor, zone, hour, dow, month)
    pred_log = float(model.predict(feats)[0])
    duration = float(np.expm1(pred_log))

    # Use direct quantile heads if available — tighter intervals.
    q_lo_model = DL.esi_quantile_low()
    q_hi_model = DL.esi_quantile_high()
    if q_lo_model is not None and q_hi_model is not None:
        log_lo = float(q_lo_model.predict(feats)[0])
        log_hi = float(q_hi_model.predict(feats)[0])
        if log_hi < log_lo:
            log_lo, log_hi = log_hi, log_lo
        duration_lo = float(np.expm1(log_lo))
        duration_hi = float(np.expm1(log_hi))
    else:
        q_lo = cal["calibration"]["q_lo"]
        q_hi = cal["calibration"]["q_hi"]
        duration_lo = float(np.expm1(pred_log + q_lo))
        duration_hi = float(np.expm1(pred_log + q_hi))

    p10, p90 = cal["duration_p10"], cal["duration_p90"]

    # Combine GBM prediction, planner-supplied duration, and kind-specific prior.
    # The dataset is dominated by short vehicle breakdowns, so for planned events
    # (stadium match, festival, VIP movement) the planner's number is far more
    # informative than the GBM. We take the max of all three.
    planner_duration = float(req.duration_min or 0)
    prior_duration = KIND_PRIOR_MIN_DURATION.get(req.event_kind, 0)
    if req.event_kind in PLANNED_KINDS:
        effective_duration = max(duration, planner_duration, float(prior_duration))
    else:
        effective_duration = duration
    duration_norm = float(np.clip(
        (effective_duration - p10) / max(p90 - p10, 1e-3), 0.0, 1.0
    ))

    # Cascade contribution: key the dict by police-station name, which is how
    # step04 actually populates it. (Looking up by zone was the bug that pinned
    # cascade_norm to zero for every input.)
    cascade_count = cal.get("cascade_count_by_zone", {}).get(seed_station or "", 0)
    cascade_norm = cascade_count / max(cal.get("cascade_count_max", 1), 1)
    corridor_vol = cal.get("corridor_volume", {}).get(corridor or "", 0)
    corridor_norm = corridor_vol / max(cal.get("corridor_volume_max", 1), 1)

    # ---- Composite ESI 0..10 -------------------------------------------
    kind_base = KIND_SEVERITY_BASE.get(req.event_kind, 3.0)
    closure_pts = 1.5 if req.requires_road_closure else 0.0
    size_pts = {"small": 0.0, "medium": 1.0, "large": 2.0}.get(req.expected_size, 1.0)
    duration_pts = 2.0 * duration_norm
    cascade_pts = 1.0 * cascade_norm
    corridor_pts = 0.7 * corridor_norm
    night_factor = 1.1 if hour >= 22 or hour <= 5 else 1.0

    raw = kind_base + closure_pts + size_pts + duration_pts + cascade_pts + corridor_pts
    esi = float(np.clip(raw * night_factor, 0.0, 10.0))

    rel_width = abs(duration_hi - duration_lo) / max(duration + 5, 5)
    band = float(np.clip(esi * 0.12 + 0.5 * rel_width, 0.4, 1.5))
    return {
        "esi": round(esi, 2),
        "low": round(max(0.0, esi - band), 2),
        "high": round(min(10.0, esi + band), 2),
        "duration_min": round(effective_duration, 1),
        "duration_low": round(max(0.0, duration_lo), 1),
        "duration_high": round(duration_hi, 1),
        "drivers": {
            "kind_base": kind_base,
            "closure_pts": closure_pts,
            "size_pts": size_pts,
            "duration_pts": round(duration_pts, 2),
            "cascade_pts": round(cascade_pts, 2),
            "corridor_pts": round(corridor_pts, 2),
            "night_factor": night_factor,
            "effective_duration_min": round(effective_duration, 1),
            "model_duration_min": round(duration, 1),
            "planner_duration_min": planner_duration,
            "prior_duration_min": prior_duration,
            "duration_norm": round(duration_norm, 2),
            "cascade_norm": round(cascade_norm, 2),
            "corridor_norm": round(corridor_norm, 2),
        },
    }


# ----- Cascade ripple -------------------------------------------------------

def _cascade_ripple(seed_station: str | None, esi: float) -> list[dict[str, Any]]:
    cas = DL.cascade()
    nodes = {n["id"]: n for n in cas.get("nodes", [])}
    edges = cas.get("edges", [])
    if not seed_station or seed_station not in nodes:
        return []

    out_edges = [e for e in edges if e["from"] == seed_station]
    out_edges.sort(key=lambda e: -e["prob"])

    ripples: list[dict[str, Any]] = []
    for e in out_edges[:8]:
        target = nodes[e["to"]]
        # confidence-aware probability scales with seed ESI
        scaled_prob = float(min(1.0, e["prob"] * (0.6 + 0.04 * esi)))
        ripples.append({
            "from": seed_station,
            "to": e["to"],
            "to_lat": target["lat"],
            "to_lng": target["lng"],
            "prob": round(scaled_prob, 3),
            "delay_min": e["delay_min"],
            "lift": e["lift"],
            "p_value": e["p_value"],
        })

    # second-order (one hop further)
    for r1 in list(ripples):
        out2 = [e for e in edges if e["from"] == r1["to"]][:3]
        for e in out2:
            target = nodes.get(e["to"])
            if target is None or e["to"] == seed_station:
                continue
            scaled = float(min(1.0, e["prob"] * r1["prob"] * 0.9))
            if scaled < 0.05:
                continue
            ripples.append({
                "from": r1["to"],
                "to": e["to"],
                "to_lat": target["lat"],
                "to_lng": target["lng"],
                "prob": round(scaled, 3),
                "delay_min": round(r1["delay_min"] + e["delay_min"], 1),
                "lift": e["lift"],
                "p_value": e["p_value"],
                "hop": 2,
            })
    return ripples


# ----- Deployment plan ------------------------------------------------------

def _eta(distance_km: float, load_factor: float) -> float:
    """Expected response time proxy: travel + dispatch overhead + load penalty."""
    return distance_km * 1.6 + 4.0 + load_factor * 6.0


def _deployment_plan(req: SimRequest, lat: float, lng: float, esi: float,
                     ripple: list[dict], hour: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stations_raw = DL.stations().get("stations", [])
    if not stations_raw:
        return [], {}

    # Officer counts scale with both ESI and event size.
    size_mult = {"small": 1.0, "medium": 1.6, "large": 2.4}.get(req.expected_size, 1.6)
    primary_units = max(2, int(round(esi * size_mult)))
    secondary_units = max(1, int(round(esi / 3.0)))

    # Demand points = the event itself + top first-hop cascade targets.
    demands: list[dict[str, Any]] = [{
        "kind": "primary", "lat": lat, "lng": lng,
        "officers": primary_units, "trigger_prob": 1.0,
    }]
    for r in [r for r in ripple if r.get("hop", 1) == 1][:3]:
        demands.append({
            "kind": "secondary", "lat": r["to_lat"], "lng": r["to_lng"],
            "officers": secondary_units, "trigger_prob": r.get("prob", 0.0),
        })

    n_d = len(demands)
    n_s = len(stations_raw)
    loads = [s["hourly_load"][hour] if s.get("hourly_load") else 0.5 for s in stations_raw]

    # Cost matrix (demand x station) of expected response time.
    cost = np.zeros((n_d, n_s))
    for i, dem in enumerate(demands):
        for j, s in enumerate(stations_raw):
            dist = DL.haversine_km(dem["lat"], dem["lng"], s["lat"], s["lng"])
            cost[i, j] = _eta(dist, loads[j])

    # --- OPTIMAL assignment (Hungarian): distinct station per demand ----
    row_idx, col_idx = linear_sum_assignment(cost)
    optimal_total = float(sum(cost[i, j] for i, j in zip(row_idx, col_idx)))

    # --- GREEDY baseline: each demand in turn grabs its nearest free station
    used: set[int] = set()
    greedy_total = 0.0
    for i in range(n_d):
        for j in np.argsort(cost[i]):
            if j in used:
                continue
            used.add(int(j))
            greedy_total += cost[i, j]
            break

    # Build the plan from the OPTIMAL assignment.
    plan: list[dict[str, Any]] = []
    for i, j in zip(row_idx, col_idx):
        dem = demands[i]
        s = stations_raw[j]
        dist = DL.haversine_km(dem["lat"], dem["lng"], s["lat"], s["lng"])
        item = {
            "kind": dem["kind"],
            "station": s["name"],
            "station_lat": s["lat"],
            "station_lng": s["lng"],
            "deploy_lat": dem["lat"],
            "deploy_lng": dem["lng"],
            "officers": dem["officers"],
            "eta_min": round(_eta(dist, loads[j]), 1),
            "distance_km": round(dist, 2),
            "load_factor": round(loads[j], 2),
        }
        if dem["kind"] == "secondary":
            item["trigger_prob"] = dem["trigger_prob"]
        plan.append(item)

    improvement = greedy_total - optimal_total
    optimization = {
        "method": "Hungarian (scipy linear_sum_assignment) over expected response-time matrix",
        "n_demands": n_d,
        "n_stations": n_s,
        "greedy_avg_eta_min": round(greedy_total / max(n_d, 1), 1),
        "optimal_avg_eta_min": round(optimal_total / max(n_d, 1), 1),
        "eta_reduction_min": round(improvement / max(n_d, 1), 2),
        "pct_faster": round(100.0 * improvement / greedy_total, 1) if greedy_total else 0.0,
    }
    return plan, optimization


# ----- Evidence gate ("I don't know" mode) ----------------------------------

def _evidence_gate(event_kind: str) -> dict[str, Any]:
    prof = DL.severity_profile()
    by_cause = prof.get("by_cause", {})
    thresholds = prof.get("evidence_thresholds", {"data_driven": 100, "limited": 20})
    cause = CAUSE_TO_DATASET.get(event_kind, "public_event")
    rec = by_cause.get(cause)
    if not rec:
        return {
            "cause": cause, "n": 0, "tier": "insufficient",
            "message": f"No historical rows for '{cause}'. Score is a planning prior only.",
            "sev_mean": None, "sev_p10": None, "sev_p90": None,
        }
    n = int(rec["n"])
    if n >= thresholds["data_driven"]:
        tier = "data_driven"
        msg = f"{n} similar historical incidents — data-driven estimate."
    elif n >= thresholds["limited"]:
        tier = "limited"
        msg = f"Only {n} similar incidents — limited evidence, interpret with caution."
    else:
        tier = "insufficient"
        msg = f"Only {n} similar incidents — insufficient evidence; score is mostly a planning prior."
    return {
        "cause": cause, "n": n, "tier": tier, "message": msg,
        "sev_mean": rec.get("sev_mean"), "sev_p10": rec.get("sev_p10"), "sev_p90": rec.get("sev_p90"),
    }


# ----- Barricades / diversions ---------------------------------------------

def _barricades(lat: float, lng: float, req: SimRequest, esi: float) -> list[dict[str, Any]]:
    if not (req.requires_road_closure or esi >= 6.5):
        return []
    # Place 4 barricades ~150 m offset N/S/E/W of the event
    deg = 0.0015
    return [
        {"lat": lat + deg, "lng": lng, "label": "B-N"},
        {"lat": lat - deg, "lng": lng, "label": "B-S"},
        {"lat": lat, "lng": lng + deg, "label": "B-E"},
        {"lat": lat, "lng": lng - deg, "label": "B-W"},
    ]


def _diversions(corridor: str | None, lat: float, lng: float) -> list[dict[str, Any]]:
    """Return up to 3 nearest alternate corridors with predicted residual load."""
    geo = DL.corridors_geojson()
    state = DL.corridor_state()
    options: list[tuple[float, str, list]] = []
    for feat in geo.get("features", []):
        name = feat["properties"]["name"]
        if name == corridor:
            continue
        coords = feat["geometry"]["coordinates"]
        # min distance to event
        d = min(DL.haversine_km(lat, lng, c[1], c[0]) for c in coords)
        options.append((d, name, coords))
    options.sort(key=lambda x: x[0])
    out: list[dict[str, Any]] = []
    for d, name, coords in options[:3]:
        st = state.get(name, {})
        residual = round(st.get("predictability", 0.5) * 0.8 * 100, 1)  # heuristic
        out.append({
            "corridor": name,
            "distance_km": round(d, 2),
            "predicted_residual_pct": residual,
            "geometry": coords,
        })
    return out


# ----- Public API ----------------------------------------------------------

def simulate(req: SimRequest) -> dict[str, Any]:
    if req.when_iso:
        when = datetime.fromisoformat(req.when_iso.replace("Z", "+00:00"))
    else:
        when = datetime.now(timezone.utc)
    when_local = when.astimezone(_IST) if _IST is not None else when
    hour = when_local.hour
    dow = when_local.weekday()
    month = when_local.month

    nearest_st = DL.nearest_station(req.lat, req.lng)
    seed_station = nearest_st["name"] if nearest_st else None

    # determine event corridor + zone via the parquet's nearest event lookup
    df = DL.events_df()
    corridor = zone = None
    if not df.empty:
        # nearest sample event spatially (cheap kNN with vector haversine)
        ds = df.sample(min(2000, len(df)), random_state=42)
        d = np.sqrt((ds["latitude"] - req.lat) ** 2 + (ds["longitude"] - req.lng) ** 2)
        r = ds.iloc[int(d.values.argmin())]
        corridor = r["corridor"] if r["corridor"] != "Unknown" else None
        zone = r["zone"] if r["zone"] != "Unknown" else None
    if corridor is None:
        corridor = DL.nearest_corridor(req.lat, req.lng)

    esi_block = _esi_score(req, corridor, zone, hour, dow, month, seed_station)
    esi = esi_block["esi"]

    # Evidence gate: tell the user when the score is a prior, not learned.
    evidence = _evidence_gate(req.event_kind)
    if evidence["tier"] == "insufficient":
        esi_block["low"] = round(max(0.0, esi - 2.5), 2)
        esi_block["high"] = round(min(10.0, esi + 2.5), 2)
        esi_block["confidence_note"] = "Wide band: insufficient historical evidence for this event kind."

    ripple = _cascade_ripple(seed_station, esi)
    plan, optimization = _deployment_plan(req, req.lat, req.lng, esi, ripple, hour)
    barricades = _barricades(req.lat, req.lng, req, esi)
    diversions = _diversions(corridor, req.lat, req.lng)

    # Total officer-minutes saved estimate (vs naive far station)
    far = max(plan, key=lambda p: p["distance_km"]) if plan else None
    naive_eta = far["eta_min"] * 1.4 if far else 0.0
    eta_saved_min = round(sum(max(0, naive_eta - p["eta_min"]) for p in plan), 1)

    return {
        "request": {
            "lat": req.lat, "lng": req.lng,
            "event_kind": req.event_kind,
            "expected_size": req.expected_size,
            "duration_min": req.duration_min,
            "requires_road_closure": req.requires_road_closure,
            "when_iso": when.isoformat() + "Z",
        },
        "context": {
            "corridor": corridor,
            "zone": zone,
            "nearest_station": seed_station,
            "hour": hour,
            "day_of_week": dow,
        },
        "esi": esi_block,
        "evidence": evidence,
        "cascade": ripple,
        "deployment": plan,
        "optimization": optimization,
        "barricades": barricades,
        "diversions": diversions,
        "summary": {
            "n_secondary_predicted": len([r for r in ripple if r.get("hop", 1) == 1]),
            "n_officers_recommended": sum(p["officers"] for p in plan),
            "est_eta_saved_min": eta_saved_min,
            "optimal_avg_eta_min": optimization.get("optimal_avg_eta_min"),
            "pct_faster_than_greedy": optimization.get("pct_faster"),
        },
    }
