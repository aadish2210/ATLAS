"""ATLAS — FastAPI entrypoint.

Run from ``backend/``:

    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import artifacts_router, copilot_router, simulator_router
from app.core import data_loader as DL
from app.core.config import settings


app = FastAPI(
    title="ATLAS",
    version="1.0.0",
    description="Astram-Trained Live-Adaptive System — event-driven congestion forecasting.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local hackathon; tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warm_caches() -> None:
    """Ensure artifacts exist, then preload them so the first request is fast."""
    required = [
        "events_clean.parquet",
        "fingerprint.json",
        "cascade_edges.json",
        "stations.json",
        "audit.json",
        "corridors.geojson",
    ]
    missing = [name for name in required if not (settings.artifacts_dir / name).exists()]

    if missing:
        print(f"[startup] Missing artifacts: {missing}; running pipeline...")
        from pipeline.run_all import main as run_pipeline

        run_pipeline()

    DL.fingerprint(); DL.cascade(); DL.stations(); DL.audit()
    DL.corridors_geojson(); DL.corridor_state(); DL.esi_calibration()
    DL.esi_model(); DL.events_df()


app.include_router(artifacts_router.router, prefix="/api", tags=["artifacts"])
app.include_router(simulator_router.router, prefix="/api", tags=["simulator"])
app.include_router(copilot_router.router, prefix="/api", tags=["copilot"])


@app.get("/")
def root() -> dict:
    return {
        "name": "ATLAS",
        "tagline": "Precognitive, self-contained, self-healing.",
        "docs": "/docs",
        "health": "/api/health",
    }
