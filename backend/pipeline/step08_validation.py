"""Step 8 — Reliability validation report for ESI predictions.

Builds an out-of-time holdout from the latest events and reports:
  * point accuracy (MAE/RMSE/median AE)
  * interval quality (90% coverage + average width)
  * slice-level reliability by event cause

Output: artifacts/validation_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402


CAT_COLS = [
    "event_cause", "corridor", "zone", "priority", "veh_type",
    "direction", "gba_identifier", "cargo_type", "desc_len_bucket",
]
NUM_COLS = [
    "hour", "dow", "is_weekend", "road_closure", "weather_flag",
    "event_kw_flag", "is_event_driven", "month", "priority_high",
    "has_veh_no", "is_commercial_veh", "has_cargo", "truck_age",
    "was_reassigned", "has_assigned_officer", "has_distinct_closer",
    "has_kgid", "has_end_address", "has_route_path", "route_points",
]
TARGET = "duration_min"


def _features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in CAT_COLS:
        if c not in out.columns:
            out[c] = "Unknown"
        out[c] = out[c].fillna("Unknown").astype(str)
    for c in NUM_COLS:
        if c not in out.columns:
            out[c] = 0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(float)
    return out[CAT_COLS + NUM_COLS]


def _safe_float(x: float) -> float:
    if pd.isna(x) or np.isinf(x):
        return 0.0
    return float(x)


def main() -> None:
    ev_path = settings.artifacts_dir / "events_clean.parquet"
    model_path = settings.artifacts_dir / "esi_model.pkl"
    cal_path = settings.artifacts_dir / "esi_calibration.json"

    if not (ev_path.exists() and model_path.exists() and cal_path.exists()):
        print("[validation] skipped (required artifacts missing)")
        return

    df = pd.read_parquet(ev_path)
    df = df.dropna(subset=[TARGET, "start_datetime"]).copy()
    df = df[(df[TARGET] > 0) & (df[TARGET] < 60 * 12)]

    if len(df) < 300:
        print("[validation] skipped (not enough rows)")
        return

    df = df.sort_values("start_datetime").reset_index(drop=True)
    holdout_n = max(200, int(round(len(df) * settings.esi_test_frac)))
    train_df = df.iloc[:-holdout_n].copy()
    holdout_df = df.iloc[-holdout_n:].copy().reset_index(drop=True)

    model = joblib.load(model_path)
    cal = json.loads(cal_path.read_text(encoding="utf-8"))
    q_lo = float(cal.get("calibration", {}).get("q_lo", -0.5))
    q_hi = float(cal.get("calibration", {}).get("q_hi", 0.5))

    Xh = _features(holdout_df)
    yh = holdout_df[TARGET].astype(float).values

    pred_log = model.predict(Xh)
    pred = np.expm1(pred_log)

    # Conformal interval (legacy)
    lo_conf = np.expm1(pred_log + q_lo)
    hi_conf = np.expm1(pred_log + q_hi)
    covered_conf = (yh >= lo_conf) & (yh <= hi_conf)

    # Direct quantile intervals (preferred when available)
    q_lo_path = settings.artifacts_dir / "esi_q05.pkl"
    q_hi_path = settings.artifacts_dir / "esi_q95.pkl"
    if q_lo_path.exists() and q_hi_path.exists():
        q_lo_model = joblib.load(q_lo_path)
        q_hi_model = joblib.load(q_hi_path)
        log_lo_q = q_lo_model.predict(Xh)
        log_hi_q = q_hi_model.predict(Xh)
        # ensure ordering element-wise
        log_lo_q, log_hi_q = np.minimum(log_lo_q, log_hi_q), np.maximum(log_lo_q, log_hi_q)
        lo_q = np.expm1(log_lo_q)
        hi_q = np.expm1(log_hi_q)
        covered_q = (yh >= lo_q) & (yh <= hi_q)
        interval_lo = lo_q
        interval_hi = hi_q
        covered = covered_q
        interval_label = "quantile_90"
    else:
        interval_lo = lo_conf
        interval_hi = hi_conf
        covered = covered_conf
        interval_label = "conformal_90"

    abs_err = np.abs(pred - yh)
    sq_err = (pred - yh) ** 2
    clipped = np.maximum(yh, 5.0)

    # -- slice helpers ----------------------------------------------------
    def _slice(group_iter, min_n: int = 40, key_name: str = "key"):
        rows = []
        for key, g in group_iter:
            if len(g) < min_n:
                continue
            idx = g.index.values
            rows.append({
                key_name: str(key),
                "n": int(len(g)),
                "mae_min": round(_safe_float(np.mean(np.abs(pred[idx] - yh[idx]))), 2),
                "coverage_90": round(_safe_float(np.mean(covered[idx])), 3),
                "avg_width_min": round(_safe_float(np.mean(interval_hi[idx] - interval_lo[idx])), 2),
            })
        rows.sort(key=lambda r: r["n"], reverse=True)
        return rows

    by_cause = _slice(holdout_df.groupby("event_cause"), key_name="cause")
    by_zone = _slice(
        holdout_df[holdout_df["zone"] != "Unknown"].groupby("zone"), key_name="zone"
    )
    holdout_df["hour_band"] = pd.cut(
        holdout_df["hour"], bins=[-1, 5, 11, 16, 21, 24],
        labels=["late_night", "morning", "midday", "evening", "night"],
    ).astype(str)
    by_hour = _slice(holdout_df.groupby("hour_band"), min_n=30, key_name="hour_band")

    report = {
        "summary": {
            "n_total": int(len(df)),
            "n_train": int(len(train_df)),
            "n_holdout": int(len(holdout_df)),
            "target": TARGET,
            "holdout_range": {
                "start": str(holdout_df["start_datetime"].min()),
                "end": str(holdout_df["start_datetime"].max()),
            },
            "interval_kind": interval_label,
            "features_used": {
                "categorical": CAT_COLS,
                "numeric": NUM_COLS,
                "count": len(CAT_COLS) + len(NUM_COLS),
            },
        },
        "metrics": {
            "mae_min": round(_safe_float(abs_err.mean()), 2),
            "median_ae_min": round(_safe_float(np.median(abs_err)), 2),
            "rmse_min": round(_safe_float(np.sqrt(sq_err.mean())), 2),
            "mape": round(_safe_float((abs_err / clipped).mean()), 3),
            "within_15_min": round(_safe_float((abs_err <= 15).mean()), 3),
            "coverage_90": round(_safe_float(covered.mean()), 3),
            "avg_interval_width_min": round(_safe_float((interval_hi - interval_lo).mean()), 2),
            "coverage_90_conformal": round(_safe_float(covered_conf.mean()), 3),
            "avg_interval_width_conformal_min": round(_safe_float((hi_conf - lo_conf).mean()), 2),
        },
        "slices": {
            "by_event_cause": by_cause[:10],
            "by_zone": by_zone[:10],
            "by_hour_band": by_hour,
        },
        "notes": [
            "Holdout is out-of-time (latest rows), not random.",
            "coverage_90 should be near 0.90 for calibrated uncertainty.",
            "interval_kind=quantile_90 uses dedicated quantile models for tighter bands.",
            "Use slice metrics to detect segments where reliability degrades.",
        ],
    }

    out_path = settings.artifacts_dir / "validation_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        "[validation] "
        f"holdout={len(holdout_df):,} "
        f"mae={report['metrics']['mae_min']:.2f}m "
        f"cov90={report['metrics']['coverage_90']:.3f}"
    )


if __name__ == "__main__":
    main()
