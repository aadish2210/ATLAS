"""Side-by-side ESI test:
  A) "Should be high" inputs grounded in actual artifacts.
  B) Chinnaswamy stadium scenario the user complained about.
Prints both ESI values and the driver breakdown so the formula's behaviour
is verifiable."""
from __future__ import annotations

import json

import requests

BASE = "http://127.0.0.1:8000/api/simulate"

CASES = {
    "A_should_be_high (Wilson Garden, construction, large, closure)": {
        "lat": 12.9556,
        "lng": 77.5857,
        "event_kind": "construction",
        "expected_size": "large",
        "duration_min": 600,
        "requires_road_closure": True,
    },
    "B_user_chinnaswamy_stadium (sports_match, large, closure, 600m)": {
        "lat": 12.9789,
        "lng": 77.5996,
        "event_kind": "sports_match",
        "expected_size": "large",
        "duration_min": 600,
        "requires_road_closure": True,
    },
}


def main() -> None:
    for label, payload in CASES.items():
        r = requests.post(BASE, json=payload, timeout=15)
        r.raise_for_status()
        sim = r.json()
        esi = sim["esi"]
        ctx = sim["context"]
        print("=" * 78)
        print(label)
        print(f"  ctx.corridor       = {ctx.get('corridor')}")
        print(f"  ctx.zone           = {ctx.get('zone')}")
        print(f"  ctx.nearest_station= {ctx.get('nearest_station')}")
        print(f"  ctx.hour           = {ctx.get('hour')}")
        print(f"  -> ESI             = {esi.get('esi')}  band=[{esi.get('low')}, {esi.get('high')}]")
        print(f"  -> predicted dur   = {esi.get('duration_min')} min")
        print(f"  drivers            = {json.dumps(esi.get('drivers'), indent=2)}")
        print(f"  officers           = {sim['summary']['n_officers_recommended']}")


if __name__ == "__main__":
    main()
