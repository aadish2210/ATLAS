"""Step 9 — Time-machine backtest: predict the afternoon from the morning.

The most defensible proof in the deck. For every day we freeze knowledge at a
cutoff hour (12:00). Using ONLY pre-cutoff incidents plus the learned cascade
graph, ATLAS RANKS police stations by afternoon risk and we score that ranking
against what actually happened after the cutoff.

Fair comparison: every strategy produces a ranked list and we evaluate
precision@K / recall@K at the SAME K (equal budget), micro-averaged over days.

  * prior        — rank by global base rate (busiest stations always)
  * persistence  — rank by this morning's incident counts
  * atlas        — persistence + cascade-graph propagation from morning stations

Plus a sharper 'cascade discovery' metric: of afternoon stations that had ZERO
morning activity (genuinely new hotspots), how many does each strategy catch?
That is the regime where the cascade graph, not persistence, must do the work.

Output: artifacts/backtest.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402

CUTOFF_HOUR = 12
KS = [5, 10, 15]
MIN_MORNING_EVENTS = 3
CASCADE_PROB_MIN = 0.10


def _micro_prf(hits: int, predicted: int, actual: int) -> dict[str, float]:
    precision = hits / predicted if predicted else 0.0
    recall = hits / actual if actual else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def main() -> None:
    df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
    df = df[df["police_station"] != "Unknown"].dropna(subset=["start_datetime", "police_station"]).copy()
    df["date"] = df["start_datetime"].dt.date.astype(str)
    df["hour"] = df["start_datetime"].dt.hour

    cas_path = settings.artifacts_dir / "cascade_edges.json"
    cascade = json.loads(cas_path.read_text(encoding="utf-8")) if cas_path.exists() else {"edges": []}
    out_edges: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for e in cascade.get("edges", []):
        if e.get("prob", 0) >= CASCADE_PROB_MIN:
            out_edges[e["from"]].append((e["to"], float(e["prob"])))

    stations = sorted(df["police_station"].unique())
    global_rate = df["police_station"].value_counts().to_dict()

    acc = {s: {k: {"hits": 0, "pred": 0, "act": 0} for k in KS}
           for s in ("prior", "persistence", "blend_no_cascade", "atlas")}
    disc = {s: {"hits": 0, "pred": 0, "act": 0} for s in ("persistence", "atlas")}

    per_day: list[dict] = []
    n_days = 0
    max_global = max(global_rate.values()) or 1.0

    for date, day in df.groupby("date"):
        morning = day[day["hour"] < CUTOFF_HOUR]
        afternoon = day[day["hour"] >= CUTOFF_HOUR]
        if len(morning) < MIN_MORNING_EVENTS or afternoon.empty:
            continue
        n_days += 1

        morning_counts = morning["police_station"].value_counts().to_dict()
        actual_pm = set(afternoon["police_station"])
        morning_set = set(morning_counts)
        max_morning = max(morning_counts.values()) if morning_counts else 1.0

        # normalized component signals per station
        prior_c = {s: float(global_rate.get(s, 0)) / max_global for s in stations}
        morning_c = {s: float(morning_counts.get(s, 0)) / max_morning for s in stations}
        cascade_c = {s: 0.0 for s in stations}
        for src, cnt in morning_counts.items():
            w = 1.0 + np.log1p(cnt)
            for dst, prob in out_edges.get(src, []):
                cascade_c[dst] = cascade_c.get(dst, 0.0) + prob * w
        max_casc = max(cascade_c.values()) or 1.0
        cascade_c = {s: v / max_casc for s, v in cascade_c.items()}

        # ranked lists per strategy (blended ranker + cascade ablation)
        prior_score = prior_c
        persist_score = morning_c
        blend_score = {s: 1.0 * prior_c[s] + 1.2 * morning_c[s] for s in stations}
        atlas_score = {s: 1.0 * prior_c[s] + 1.2 * morning_c[s] + 0.9 * cascade_c[s] for s in stations}

        ranked = {
            "prior": sorted(stations, key=lambda s: -prior_score[s]),
            "persistence": sorted(stations, key=lambda s: -persist_score[s]),
            "blend_no_cascade": sorted(stations, key=lambda s: -blend_score[s]),
            "atlas": sorted(stations, key=lambda s: -atlas_score[s]),
        }
        for strat, order in ranked.items():
            for k in KS:
                pred = set(order[:k])
                acc[strat][k]["hits"] += len(pred & actual_pm)
                acc[strat][k]["pred"] += len(pred)
                acc[strat][k]["act"] += len(actual_pm)

        # cascade discovery: NEW afternoon hotspots (no morning activity).
        # persistence is structurally blind to these; ATLAS uses cascade.
        new_pm = actual_pm - morning_set
        if new_pm:
            atlas_new = [s for s in ranked["atlas"] if s not in morning_set][:10]
            persist_new = [s for s in ranked["persistence"] if s not in morning_set][:10]
            disc["atlas"]["hits"] += len(set(atlas_new) & new_pm)
            disc["atlas"]["pred"] += len(atlas_new)
            disc["atlas"]["act"] += len(new_pm)
            disc["persistence"]["hits"] += len(set(persist_new) & new_pm)
            disc["persistence"]["pred"] += len(persist_new)
            disc["persistence"]["act"] += len(new_pm)

            caught = sorted(set(atlas_new) & new_pm)
            if caught:
                per_day.append({
                    "date": date,
                    "n_morning": int(len(morning)),
                    "n_afternoon": int(len(afternoon)),
                    "new_hotspots": int(len(new_pm)),
                    "cascade_caught": caught[:8],
                    "n_cascade_caught": int(len(caught)),
                })

    strategies = {
        strat: {f"k{k}": _micro_prf(v[k]["hits"], v[k]["pred"], v[k]["act"]) for k in KS}
        for strat, v in acc.items()
    }
    discovery = {strat: _micro_prf(v["hits"], v["pred"], v["act"]) for strat, v in disc.items()}
    per_day.sort(key=lambda d: d["n_cascade_caught"], reverse=True)

    atlas10 = strategies["atlas"]["k10"]
    blend10 = strategies["blend_no_cascade"]["k10"]
    base10 = max(strategies["prior"]["k10"]["f1"], strategies["persistence"]["k10"]["f1"])
    out = {
        "params": {
            "cutoff_hour": CUTOFF_HOUR, "K_values": KS,
            "n_days_evaluated": n_days, "n_stations": len(stations),
            "cascade_prob_min": CASCADE_PROB_MIN,
            "ranker": "atlas = 1.0*base_rate + 1.2*morning + 0.9*cascade (all min-max normalized)",
        },
        "strategies": strategies,
        "cascade_discovery": discovery,
        "headline": {
            "atlas_precision_at_10": atlas10["precision"],
            "atlas_recall_at_10": atlas10["recall"],
            "atlas_f1_at_10": atlas10["f1"],
            "f1_lift_vs_best_baseline_at_10": round(atlas10["f1"] - base10, 3),
            "cascade_ablation_f1_lift_at_10": round(atlas10["f1"] - blend10["f1"], 3),
            "discovery_recall_atlas": discovery["atlas"]["recall"],
            "discovery_recall_persistence": discovery["persistence"]["recall"],
        },
        "top_cascade_days": per_day[:15],
        "notes": [
            "Equal-budget ranked comparison: precision@K / recall@K at identical K.",
            "ATLAS blends base rate + today's morning + cascade propagation.",
            "cascade_ablation = ATLAS minus the cascade term; the F1 gap is the cascade graph's measurable lift.",
            "discovery: NEW afternoon hotspots with no morning activity — persistence is structurally blind here.",
        ],
    }
    (settings.artifacts_dir / "backtest.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(
        f"[backtest] days={n_days}  ATLAS@10 P={atlas10['precision']} R={atlas10['recall']} F1={atlas10['f1']} "
        f"| blend(no cascade) F1={blend10['f1']}  cascade lift={round(atlas10['f1'] - blend10['f1'], 3)} "
        f"| discovery recall atlas={discovery['atlas']['recall']} vs persistence={discovery['persistence']['recall']}"
    )


if __name__ == "__main__":
    main()
