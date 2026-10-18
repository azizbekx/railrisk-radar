"""Live supplier tracking API: the organisation's real suppliers, the daily agent run, the portfolio and one supplier's detail."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.common import NO_BUFFER, _line, jsonable, stream
from core import tracking

router = APIRouter(prefix="/tracking")


class NewSupplier(BaseModel):
    name: str
    website: str = ""
    country: str = ""
    category: str = ""
    criticality: str = "Medium"
    dataset_id: str | None = None
    relationship: str = ""  # what they supply us, e.g. "brakes for Velaro"
    source: str = ""  # link that documents the supply relationship


class RunIn(BaseModel):
    ids: list[str] = []


@router.get("")
def get_portfolio():
    return jsonable(tracking.portfolio())


@router.post("/suppliers")
def add(body: NewSupplier):
    try:
        return jsonable(tracking.add_supplier(**body.model_dump()))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/suppliers/{sid}")
def remove(sid: str):
    try:
        tracking.remove_supplier(sid)
    except KeyError:
        raise HTTPException(404, "Unknown tracked supplier")
    return {"ok": True}


@router.post("/sample")
def sample():
    return jsonable(tracking.add_sample())


@router.post("/run")
def run(body: RunIn | None = None):
    if tracking.RUN_LOCK.locked():
        return StreamingResponse(iter([_line("error", "A tracking run is already in progress")]),
                                 media_type="application/x-ndjson", headers=NO_BUFFER)
    return stream(tracking.run, ids=body.ids if body else None, trigger="manual")


@router.get("/supplier/{sid}")
def get_detail(sid: str):
    try:
        return jsonable(tracking.detail(sid))
    except KeyError:
        raise HTTPException(404, "Unknown tracked supplier")
