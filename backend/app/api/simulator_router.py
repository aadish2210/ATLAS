"""POST /api/simulate — the click-to-drop event simulator."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.models.simulator import SimRequest, simulate


router = APIRouter()


class SimulateBody(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    event_kind: str = Field("rally")
    expected_size: str = Field("medium")
    duration_min: int = Field(60, ge=1, le=24 * 60)
    requires_road_closure: bool = False
    when_iso: str | None = None


@router.post("/simulate")
def simulate_event(body: SimulateBody) -> dict:
    req = SimRequest(
        lat=body.lat, lng=body.lng,
        event_kind=body.event_kind,
        expected_size=body.expected_size,
        duration_min=body.duration_min,
        requires_road_closure=body.requires_road_closure,
        when_iso=body.when_iso,
    )
    return simulate(req)
