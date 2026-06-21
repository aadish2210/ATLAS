"""Explain cascade + deployment with REAL numbers from the artifacts.
Throwaway teaching script."""
from __future__ import annotations

import json

from app.core.config import settings
from app.core import data_loader as DL


def show_cascade() -> None:
    c = json.loads((settings.artifacts_dir / "cascade_edges.json").read_text())
    edges = sorted(c["edges"], key=lambda x: -x["prob"])[:6]
    print("=" * 70)
    print("TOP CASCADE LINKS ATLAS LEARNED (from real co-occurrences)")
    print("=" * 70)
    for x in edges:
        print(
            f"  {x['from']:>18}  ->  {x['to']:<18} "
            f"prob={x['prob']:.2f}  lift x{x['lift']:.1f}  "
            f"~{x['delay_min']:.0f} min  p={x['p_value']:.3f}"
        )
    print()
    print(f"Graph totals: {len(c['nodes'])} stations, {len(c['edges'])} significant links")


def show_deployment() -> None:
    from app.models.simulator import SimRequest, simulate

    req = SimRequest(
        lat=12.9789, lng=77.5996,
        event_kind="festival", expected_size="large",
        duration_min=300, requires_road_closure=True,
    )
    sim = simulate(req)
    print()
    print("=" * 70)
    print("DEPLOYMENT for a large festival dropped near Chinnaswamy stadium")
    print("=" * 70)
    print(f"  ESI (severity 0-10): {sim['esi']['esi']}")
    print(f"  Officers recommended: {sim['summary']['n_officers_recommended']}")
    o = sim["optimization"]
    print(f"  Demands (event + predicted spillover): {o['n_demands']}")
    print(f"  Greedy avg response : {o['greedy_avg_eta_min']} min")
    print(f"  Optimal avg response: {o['optimal_avg_eta_min']} min  ({o['pct_faster']}% faster)")
    print()
    print("  Who goes where:")
    for d in sim["deployment"]:
        print(
            f"    [{d['kind']:<9}] {d['station']:<18} "
            f"{d['officers']} officer(s)  ETA {d['eta_min']:.0f} min  "
            f"{d['distance_km']:.1f} km  load {int(d['load_factor']*100)}%"
        )


if __name__ == "__main__":
    show_cascade()
    show_deployment()
