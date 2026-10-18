"""compare page API. Owned by the compare slice.

POST /api/compare: everything the "Compare shortlist" page needs in one response —
ranking, per-supplier scores (for the heatmap / profile overlay), TRI composition by
risk family, dataset means and best/worst per column.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from api.common import jsonable, lens_weights, row
from core import dataset as ds

router = APIRouter()

MAX_IDS = 20


class CompareIn(BaseModel):
    ids: list[str]
    lens_weights: dict | None = None


@router.post("/compare")
def compare(body: CompareIn):
    ids = [i for i in dict.fromkeys(body.ids) if i in ds.df().index][:MAX_IDS]
    if len(ids) < 2:
        return jsonable({"ids": ids, "ranking": [], "scores": {}, "levels": {}, "score_order": ds.SCORES,
                         "families": ds.GROUPS, "tri_composition": {}, "means": {}, "columns": {}})

    w = lens_weights(body.lens_weights)
    use_lens = bool(body.lens_weights)
    d = ds.df().loc[ids].copy()
    d["Lens index"] = ds.lens_index(d, w)
    sort_cols = ["Lens index", "Total_Risk_Index"] if use_lens else ["Total_Risk_Index"]
    d = d.sort_values(sort_cols)
    order = d.index.tolist()

    # which scores each supplier is uniquely best (lowest risk) at within this set
    best_at: dict[str, list[str]] = {sid: [] for sid in order}
    for c in ds.SCORES:
        winners = d.index[d[c] == d[c].min()]
        if len(winners) == 1:
            best_at[winners[0]].append(ds.label(c))
    worst_col = d[ds.SCORES].idxmax(axis=1)

    ranking = []
    for rank, sid in enumerate(order, start=1):
        r = d.loc[sid]
        ranking.append({
            "rank": rank, "id": sid, "name": r["Supplier Name"], "tri": int(r["Total_Risk_Index"]),
            "level": r["Total_Risk_Index_Level"], "lens_index": float(r["Lens index"]) if use_lens else None,
            "critical_scores": int((r[ds.SCORES] >= 75).sum()),
            "worst_label": ds.label(worst_col[sid]), "worst_value": int(r[worst_col[sid]]),
            "best_at": best_at[sid], "delivery": float(r["Supplier Delivery Rating"]),
            "confirmation": float(r["Order Confirmation Rate"]), "change": float(r["Order Change Rate"]),
            "po": float(r[ds.PO]), "sourcing": r["Sourcing Risk Level"], "complexity": r["Supply Chain Complexity"],
        })

    scores = {sid: {c: int(d.at[sid, c]) for c in ds.SCORES} for sid in order}
    levels = {sid: {c: d.at[sid, f"{c}_Level"] for c in ds.SCORES} for sid in order}
    tri_composition = {
        sid: {g: round(float(sum(d.at[sid, c] * ds.TRI_WEIGHTS[c] for c in cols)), 1) for g, cols in ds.GROUPS.items()}
        for sid in order
    }
    means = ds.means().round(2).to_dict()
    columns = ds.compare(order, ["Total_Risk_Index"] + ds.SCORES + ds.OPS)["columns"]

    return jsonable({
        "ids": order, "lens_label": "Lens index" if use_lens else "TRI", "rows": [row(sid, body.lens_weights) for sid in order],
        "ranking": ranking, "scores": scores, "levels": levels, "score_order": ds.SCORES, "families": ds.GROUPS,
        "tri_composition": tri_composition, "means": means, "columns": columns,
    })
