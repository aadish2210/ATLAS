"""Step 11 — Learned severity target + evidence index.

There is no `severity` column in the data, so we DERIVE one from observed
outcomes (what actually happened), using robust percentile ranks so a single
19,000-minute outlier cannot dominate:

    severity = 10 * ( 0.45 * rank(duration)
                    + 0.25 * rank(response)
                    + 0.15 * road_closure
                    + 0.15 * rank(station_cascade_count) )

This is a data-defined target, not hand-tuned weights on the live score.

We then build an EVIDENCE INDEX so the live system can say "I don't know":
for every event_cause (and cause x hour-band) we record how many historical
rows support it plus the empirical severity distribution. The simulator uses
the count to gate confidence:

    n >= 100  -> data-driven        (narrow band)
    20..99    -> limited evidence   (wider band, caution)
    < 20      -> insufficient       (refuse a hard number)

Output: artifacts/severity_profile.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402

HOUR_BANDS = [(-1, 5, "late_night"), (5, 11, "morning"),
              (11, 16, "midday"), (16, 21, "evening"), (21, 24, "night")]


def _hour_band(h: int) -> str:
    for lo, hi, name in HOUR_BANDS:
        if lo < h <= hi:
            return name
    return "midday"


def _rank(series: pd.Series) -> pd.Series:
    """Empirical percentile rank in [0,1], robust to outliers."""
    return series.rank(pct=True).fillna(0.0)


def main() -> None:
    df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
    df = df.copy()

    # station cascade out-degree count, joined per row
    cas_path = settings.artifacts_dir / "cascade_edges.json"
    cascade_count: dict[str, int] = {}
    if cas_path.exists():
        cas = json.loads(cas_path.read_text(encoding="utf-8"))
        for e in cas.get("edges", []):
            cascade_count[e["from"]] = cascade_count.get(e["from"], 0) + 1
    df["station_cascade"] = df["police_station"].map(cascade_count).fillna(0).astype(float)

    dur = pd.to_numeric(df.get("duration_min"), errors="coerce")
    resp = pd.to_numeric(df.get("response_min"), errors="coerce")
    closure = pd.to_numeric(df.get("road_closure"), errors="coerce").fillna(0).clip(0, 1)

    severity = 10.0 * (
        0.45 * _rank(dur)
        + 0.25 * _rank(resp)
        + 0.15 * closure
        + 0.15 * _rank(df["station_cascade"])
    )
    df["severity_observed"] = severity.clip(0, 10)
    df["hour_band"] = df["hour"].map(_hour_band)

    def _dist(g: pd.DataFrame) -> dict:
        s = g["severity_observed"]
        return {
            "n": int(len(g)),
            "sev_mean": round(float(s.mean()), 2),
            "sev_p10": round(float(np.percentile(s, 10)), 2),
            "sev_p50": round(float(np.percentile(s, 50)), 2),
            "sev_p90": round(float(np.percentile(s, 90)), 2),
            "dur_p50": round(float(pd.to_numeric(g["duration_min"], errors="coerce").median() or 0), 1),
        }

    by_cause = {str(c): _dist(g) for c, g in df.groupby("event_cause") if c != "Unknown"}
    by_cause_hour = {
        f"{c}|{hb}": _dist(g)
        for (c, hb), g in df.groupby(["event_cause", "hour_band"])
        if c != "Unknown" and len(g) >= 5
    }

    out = {
        "target_formula": "10*(0.45*rank(dur)+0.25*rank(resp)+0.15*closure+0.15*rank(station_cascade))",
        "global": {
            "sev_mean": round(float(df["severity_observed"].mean()), 2),
            "sev_p90": round(float(np.percentile(df["severity_observed"], 90)), 2),
        },
        "evidence_thresholds": {"data_driven": 100, "limited": 20},
        "by_cause": by_cause,
        "by_cause_hour": by_cause_hour,
        "notes": [
            "severity_observed is derived from outcomes, not hand-tuned on the live score.",
            "by_cause.n is the evidence count the simulator uses to gate confidence.",
        ],
    }
    path = settings.artifacts_dir / "severity_profile.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(
        f"[severity] causes={len(by_cause)} "
        f"global_mean={out['global']['sev_mean']} "
        f"(thin causes <20 rows will be gated as 'insufficient')"
    )


if __name__ == "__main__":
    main()
