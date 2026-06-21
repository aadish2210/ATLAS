"""Step 4 — Event Severity Index (ESI) regressor with conformal intervals.

Trains a GradientBoosting model that predicts log(duration_min) from event
features. Conformal calibration on a held-out split gives a valid 90%
prediction interval that the UI shows under every ESI estimate.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

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


@dataclass
class Calibration:
    alpha: float
    q_lo: float
    q_hi: float
    rmse_log: float
    n_train: int
    n_calibrate: int


def _features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in CAT_COLS:
        if c not in df.columns:
            df[c] = "Unknown"
        df[c] = df[c].fillna("Unknown").astype(str)
    for c in NUM_COLS:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(float)
    return df[CAT_COLS + NUM_COLS]


def main() -> None:
    df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
    df = df.dropna(subset=[TARGET]).copy()
    df = df[(df[TARGET] > 0) & (df[TARGET] < 60 * 12)]  # cap at 12h
    print(f"[esi] training rows: {len(df):,}")

    X = _features(df)
    y = np.log1p(df[TARGET].values)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=settings.esi_test_frac, random_state=42
    )

    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=10), CAT_COLS),
        ("num", "passthrough", NUM_COLS),
    ])
    model = Pipeline([
        ("pre", pre),
        ("gbm", GradientBoostingRegressor(
            n_estimators=400, max_depth=4, learning_rate=0.05,
            subsample=0.85, random_state=42,
        )),
    ])
    model.fit(X_tr, y_tr)

    # ---- quantile regression heads for direct prediction intervals ------
    # Two narrow GBMs trained on the 5th / 95th quantile of log-duration.
    # Gives much tighter, more informative bands than a single conformal width.
    q_lo_pipeline = Pipeline([
        ("pre", pre),
        ("gbm", GradientBoostingRegressor(
            loss="quantile", alpha=0.05,
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.85, random_state=42,
        )),
    ])
    q_hi_pipeline = Pipeline([
        ("pre", pre),
        ("gbm", GradientBoostingRegressor(
            loss="quantile", alpha=0.95,
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.85, random_state=42,
        )),
    ])
    q_lo_pipeline.fit(X_tr, y_tr)
    q_hi_pipeline.fit(X_tr, y_tr)

    # ---- conformal calibration ------------------------------------------
    pred_te = model.predict(X_te)
    residuals = np.abs(y_te - pred_te)
    alpha = settings.esi_calibration_alpha
    q = float(np.quantile(residuals, 1 - alpha))

    rmse_log = float(np.sqrt(((y_te - pred_te) ** 2).mean()))
    calib = Calibration(alpha=alpha, q_lo=-q, q_hi=q,
                        rmse_log=rmse_log,
                        n_train=len(X_tr), n_calibrate=len(X_te))

    # ---- ESI normalization stats ----------------------------------------
    pred_full = model.predict(X)
    dur_pred = np.expm1(pred_full)
    duration_p10, duration_p90 = float(np.percentile(dur_pred, 10)), float(np.percentile(dur_pred, 90))

    # cascade and corridor criticality — pulled from artifacts written by step03/step02
    cascade_path = settings.artifacts_dir / "cascade_edges.json"
    cascade_count: dict[str, int] = {}
    if cascade_path.exists():
        c = json.loads(cascade_path.read_text())
        for e in c["edges"]:
            cascade_count[e["from"]] = cascade_count.get(e["from"], 0) + 1
    cascade_max = max(cascade_count.values(), default=1) or 1

    corridor_volume = df.groupby("corridor").size().to_dict()
    corridor_max = max(corridor_volume.values()) if corridor_volume else 1

    artifacts = {
        "calibration": asdict(calib),
        "duration_p10": duration_p10,
        "duration_p90": duration_p90,
        "cascade_count_by_zone": cascade_count,
        "cascade_count_max": cascade_max,
        "corridor_volume": corridor_volume,
        "corridor_volume_max": corridor_max,
        "target": TARGET,
        "features": {"categorical": CAT_COLS, "numeric": NUM_COLS},
    }
    (settings.artifacts_dir / "esi_calibration.json").write_text(json.dumps(artifacts, indent=2))

    joblib.dump(model, settings.artifacts_dir / "esi_model.pkl")
    joblib.dump(q_lo_pipeline, settings.artifacts_dir / "esi_q05.pkl")
    joblib.dump(q_hi_pipeline, settings.artifacts_dir / "esi_q95.pkl")
    print(f"[esi] saved model rmse(log)={rmse_log:.3f} q90={q:.3f} (+ q05/q95 heads)")


if __name__ == "__main__":
    main()
