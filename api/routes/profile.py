"""profile page API. Owned by the profile slice."""
import json

from fastapi import APIRouter, HTTPException, Query

from api.common import jsonable, row
from core import dataset as ds

router = APIRouter()


@router.get("/profile/{ref}")
def profile(ref: str, lens: str | None = Query(None, description="JSON-encoded lens weights, e.g. the active buyer lens")):
    """Full profile for one supplier: exact TRI decomposition, a waterfall vs the dataset average,
    operational metrics and lower-risk swap candidates. 404 if the reference doesn't resolve."""
    sid = ds.resolve(ref)
    if not sid:
        raise HTTPException(404, f"Unknown supplier '{ref}'")
    r = ds.df().loc[sid]
    e = ds.explain(sid)
    out_row = row(sid)
    if lens:
        try:
            w = ds.normalize_weights(json.loads(lens))
            out_row["lens_index"] = round(sum(float(r[c]) * v for c, v in w.items()), 1)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # waterfall: dataset average TRI -> this supplier's TRI, one step per score (already sorted by impact),
    # plus a rounding residual so the steps always land exactly on the real TRI.
    cum = e["dataset_average_tri"]
    waterfall = []
    for p in e["contributions"]:
        start = cum
        cum = round(cum + p["vs_average"], 2)
        waterfall.append({"label": p["label"], "delta": p["vs_average"], "start": start, "end": cum,
                          "value": p["value"], "weight": p["weight"], "points": p["points"]})
    residual = round(e["total_risk_index"] - cum, 2)
    if abs(residual) > 0.05:
        waterfall.append({"label": "Rounding", "delta": residual, "start": cum, "end": e["total_risk_index"],
                          "value": None, "weight": None, "points": None})

    alt = ds.similar_lower_risk(sid, 6)
    alternatives = []
    for aid in alt.index:
        ar = row(aid)
        ar["tri_delta"] = e["total_risk_index"] - ar["tri"]
        alternatives.append(ar)

    return jsonable({
        "id": sid, "row": out_row, "narrative": ds.narrative(sid),
        "total_risk_index": e["total_risk_index"], "level": e["level"],
        "riskier_than_pct": e["riskier_than_pct"], "dataset_average_tri": e["dataset_average_tri"],
        "formula": e["formula"], "recomputed": e["recomputed"],
        "sourcing_risk_level": e["sourcing_risk_level"], "supply_chain_complexity": e["supply_chain_complexity"],
        "po_volume": float(r[ds.PO]),
        "contributions": e["contributions"], "waterfall": waterfall,
        "operational_metrics": e["operational_metrics"],
        "alternatives": alternatives,
    })
