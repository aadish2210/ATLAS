"""Step 7 — Corridor geometry approximation.

The dataset only has point lat/lng — no road polylines. We approximate each
named corridor as a smoothed polyline through KMeans waypoints ordered along
the principal-component axis of the events on that corridor.

Outputs:
  * corridors.geojson   — LineString features per corridor with metadata
  * corridor_state.json — per corridor x hour: predicted ESI band (drives the
                           breathing animation in the UI)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402

MIN_CORRIDOR_EVENTS = 25
MAX_WAYPOINTS = 14
MIN_WAYPOINTS = 4


def _smooth(points: np.ndarray, iterations: int = 2) -> np.ndarray:
    """Chaikin curve smoothing."""
    pts = points
    for _ in range(iterations):
        if len(pts) < 3:
            break
        new_pts = [pts[0]]
        for i in range(len(pts) - 1):
            p, q = pts[i], pts[i + 1]
            new_pts.append(p * 0.75 + q * 0.25)
            new_pts.append(p * 0.25 + q * 0.75)
        new_pts.append(pts[-1])
        pts = np.array(new_pts)
    return pts


def _polyline(events: pd.DataFrame) -> list[list[float]]:
    pts = events[["longitude", "latitude"]].values
    n = len(pts)
    if n < 3:
        return pts.tolist()
    k = max(MIN_WAYPOINTS, min(MAX_WAYPOINTS, int(np.sqrt(n))))

    km = KMeans(n_clusters=k, n_init=5, random_state=42).fit(pts)
    centroids = km.cluster_centers_

    # order centroids along principal component (rough corridor axis)
    pca = PCA(n_components=1).fit(pts)
    proj = pca.transform(centroids)[:, 0]
    order = np.argsort(proj)
    ordered = centroids[order]

    smoothed = _smooth(ordered)
    return smoothed.tolist()


def main() -> None:
    df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
    fp = json.loads((settings.artifacts_dir / "fingerprint.json").read_text())
    print(f"[corridors] events: {len(df):,}")

    features = []
    state: dict[str, dict] = {}
    for name, g in df.groupby("corridor"):
        if name in {"Unknown", "Non-corridor"} or len(g) < MIN_CORRIDOR_EVENTS:
            continue
        coords = _polyline(g)
        meta = fp["corridors"].get(name, {})
        predictability = meta.get("predictability", 0.0)
        breathing = meta.get("breathing", [0] * 24)
        weather_share = meta.get("weather_share", 0.0)
        closure_share = meta.get("closure_share", 0.0)

        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "name": name,
                "events": int(len(g)),
                "predictability": predictability,
                "weather_share": weather_share,
                "closure_share": closure_share,
                "criticality": round(min(1.0, len(g) / 800.0), 3),
            },
        })
        state[name] = {
            "events": int(len(g)),
            "predictability": predictability,
            "breathing": breathing,
            "weather_share": weather_share,
            "closure_share": closure_share,
            "esi_by_hour": [round(min(10.0, b * 10.0), 2) for b in breathing],
        }

    geojson = {"type": "FeatureCollection", "features": features}
    (settings.artifacts_dir / "corridors.geojson").write_text(json.dumps(geojson))
    (settings.artifacts_dir / "corridor_state.json").write_text(json.dumps(state, indent=2))
    print(f"[corridors] wrote {len(features)} corridors")


if __name__ == "__main__":
    main()
