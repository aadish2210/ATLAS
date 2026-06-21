"""Central configuration. Single source of truth for paths + tunables."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = (
    BACKEND_ROOT.parent if (BACKEND_ROOT.parent / "backend").exists() else BACKEND_ROOT
)
ARTIFACTS_DIR = BACKEND_ROOT / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _find_raw_csv() -> Path:
    candidates = [
        PROJECT_ROOT / "data" / "astram_events.csv",
        BACKEND_ROOT / "data" / "astram_events.csv",
        PROJECT_ROOT / "Astram event data_anonymized - Astram event data_anonymizedb40ac87.csv",
        BACKEND_ROOT / "Astram event data_anonymized - Astram event data_anonymizedb40ac87.csv",
        *PROJECT_ROOT.glob("Astram event data_anonymized*.csv"),
        *BACKEND_ROOT.glob("Astram event data_anonymized*.csv"),
        *PROJECT_ROOT.glob("data/Astram event data_anonymized*.csv"),
        *BACKEND_ROOT.glob("data/Astram event data_anonymized*.csv"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return PROJECT_ROOT / "Astram event data_anonymized - Astram event data_anonymizedb40ac87.csv"


@dataclass(frozen=True)
class Settings:
    raw_csv_path: Path = field(default_factory=_find_raw_csv)
    artifacts_dir: Path = ARTIFACTS_DIR

    # Bengaluru bounding box (drop noise points outside)
    bbox_lat_min: float = 12.70
    bbox_lat_max: float = 13.25
    bbox_lng_min: float = 77.35
    bbox_lng_max: float = 77.85

    # Theme-aligned event causes (the planning subset)
    event_driven_causes: tuple[str, ...] = (
        "public_event", "procession", "vip_movement", "protest", "construction",
    )

    # Cascade detection windows
    cascade_radius_km: float = 5.0
    cascade_window_min: int = 60
    cascade_decay_min: float = 30.0     # exponential decay half-life
    cascade_n_permutations: int = 200
    cascade_min_lift: float = 1.5
    cascade_max_p: float = 0.05

    # ESI training
    esi_test_frac: float = 0.20
    esi_calibration_alpha: float = 0.10  # 90% conformal interval

    # Stations
    station_min_events: int = 20

    # Time
    bengaluru_tz: str = "Asia/Kolkata"


settings = Settings()
