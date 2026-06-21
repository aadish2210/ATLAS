"""One-shot orchestrator.

Run from the ``backend/`` directory:

    python -m pipeline.run_all
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow `python pipeline/run_all.py` as well as `python -m pipeline.run_all`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import (  # noqa: E402
    step01_clean,
    step02_fingerprint,
    step03_cascade,
    step04_esi,
    step05_stations,
    step06_audit,
    step07_corridors,
    step08_validation,
    step09_backtest,
    step10_semantic,
    step11_severity,
)


STEPS = [
    ("01-clean", step01_clean.main),
    ("02-fingerprint", step02_fingerprint.main),
    ("03-cascade", step03_cascade.main),
    ("04-esi", step04_esi.main),
    ("05-stations", step05_stations.main),
    ("06-audit", step06_audit.main),
    ("07-corridors", step07_corridors.main),
    ("08-validation", step08_validation.main),
    ("09-backtest", step09_backtest.main),
    ("10-semantic", step10_semantic.main),
    ("11-severity", step11_severity.main),
]


def main() -> None:
    total = time.time()
    for name, fn in STEPS:
        t0 = time.time()
        print(f"\n=== {name} ===")
        fn()
        print(f"=== {name} done in {time.time()-t0:.2f}s ===")
    print(f"\n[run_all] total {time.time()-total:.2f}s")


if __name__ == "__main__":
    main()
