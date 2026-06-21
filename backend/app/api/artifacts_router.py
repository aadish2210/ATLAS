"""Routes that just expose precomputed artifacts (read-only)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core import data_loader as DL


router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "loaded": DL.all_loaded()}


@router.get("/city")
def city() -> dict:
    fp = DL.fingerprint()
    return {
        "city": fp.get("city", {}),
        "n_corridors": fp.get("n_corridors", 0),
        "dvi": fp.get("dvi", {}),
    }


@router.get("/corridors")
def corridors() -> dict:
    return DL.corridors_geojson()


@router.get("/corridors/state")
def corridor_state() -> dict:
    return DL.corridor_state()


@router.get("/corridors/{name}/fingerprint")
def corridor_fingerprint(name: str) -> dict:
    fp = DL.fingerprint().get("corridors", {})
    if name not in fp:
        raise HTTPException(status_code=404, detail=f"corridor '{name}' not found")
    return {"name": name, **fp[name]}


@router.get("/stations")
def stations() -> dict:
    return DL.stations()


@router.get("/cascade")
def cascade() -> dict:
    return DL.cascade()


@router.get("/audit")
def audit() -> dict:
    return DL.audit()


@router.get("/fingerprint")
def fingerprint() -> dict:
    return DL.fingerprint()


@router.get("/validation")
def validation() -> dict:
    return DL.validation_report()


@router.get("/backtest")
def backtest() -> dict:
    return DL.backtest()


@router.get("/semantic")
def semantic() -> dict:
    return DL.semantic()


@router.get("/severity")
def severity() -> dict:
    return DL.severity_profile()


@router.get("/replay")
def replay(date: str) -> dict:
    return DL.replay_timeline(date)
