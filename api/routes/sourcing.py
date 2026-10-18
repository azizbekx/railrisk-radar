"""Find suppliers (sourcing agent) API: the buyer's request -> 50 RFQs -> 7 finalists -> 3 recommended. Logic in core/sourcing.py."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.common import jsonable, last, remember, stream
from core import dataset as ds, sourcing

router = APIRouter(prefix="/sourcing")


@router.get("/catalog")
def catalog():
    return jsonable({k: {"label": v["label"], "part_type": v["part_type"], "unit_eur": v["unit_eur"], "lead_weeks": v["lead_weeks"],
                         "certs": v["certs"]} for k, v in sourcing.COMPONENTS.items()})


class ParseIn(BaseModel):
    text: str


@router.post("/parse")
def parse(body: ParseIn):
    return jsonable(sourcing.parse_request(body.text))


class RunIn(BaseModel):
    component: str = ""
    text: str = ""  # used to fill the brief when no component is given
    quantity: int | None = None
    need_by_weeks: int | None = None
    target_unit_price: float | None = None
    notes: str = ""
    lens_name: str | None = None
    lens_weights: dict | None = None


@router.post("/run")
def run(body: RunIn):
    b = body.model_dump()
    if b["component"] not in sourcing.COMPONENTS:
        if not b["text"].strip():
            raise HTTPException(400, "Pick a component or describe what you need")
        parsed = sourcing.parse_request(b["text"])
        if parsed["component"] not in sourcing.COMPONENTS:
            raise HTTPException(400, "Could not tell which component you need; pick one from the list")
        b = {**b, **{k: b[k] or parsed[k] for k in ("component", "quantity", "need_by_weeks", "target_unit_price")},
             "notes": b["notes"] or parsed.get("notes") or ""}
    if b["notes"] == "" and b["text"].strip():
        b["notes"] = b["text"].strip()[:300]
    if b["lens_weights"]:
        b["lens_weights"] = ds.normalize_weights(b["lens_weights"])

    def go(log=None):
        res = sourcing.run(b["component"], b["quantity"], b["need_by_weeks"], b["target_unit_price"], b["notes"],
                           b["lens_name"], b["lens_weights"], log=log)
        remember("sourcing", res)
        return res

    return stream(go)


@router.get("/last")
def get_last():
    return jsonable(last("sourcing"))
