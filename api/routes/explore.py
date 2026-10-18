"""explore page API. Owned by the explore slice: filter/rank/shortlist the 10,000 suppliers."""
import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.common import jsonable
from core import dataset as ds

router = APIRouter()

SORT_COLS = {
    "tri": "Total_Risk_Index", "lens_index": "Lens_Index", "delivery": "Supplier Delivery Rating",
    "confirmation": "Order Confirmation Rate", "change": "Order Change Rate", "po": ds.PO,
    "percentile": "TRI_Percentile", "name": "Supplier Name",
}


class Filters(BaseModel):
    tri_min: float = 0
    tri_max: float = 100
    levels: list[str] = Field(default_factory=list)
    sourcing: list[str] = Field(default_factory=list)
    complexity: list[str] = Field(default_factory=list)
    delivery_min: float = 0
    confirmation_min: float = 0
    change_max: float = 100
    po_min: float = 0
    po_max: float = 1e12
    knockout: list[str] = Field(default_factory=list)  # score keys: exclude Critical-level in these
    max_score: float = 100  # drop suppliers whose worst individual score exceeds this
    text: str = ""


class QueryIn(BaseModel):
    filters: Filters = Field(default_factory=Filters)
    lens_weights: dict | None = None
    sort: str = "tri"
    ascending: bool = True
    limit: int = 300


def _rows(d: pd.DataFrame, has_lens: bool) -> list[dict]:
    out = []
    worst = d[ds.SCORES].idxmax(axis=1) if len(d) else pd.Series([], dtype=str)
    for sid, r in d.iterrows():
        row = {"id": sid, "name": r["Supplier Name"], "tri": int(r["Total_Risk_Index"]),
               "level": r["Total_Risk_Index_Level"], "tri_percentile": float(r["TRI_Percentile"]),
               "sourcing": r["Sourcing Risk Level"], "complexity": r["Supply Chain Complexity"],
               "delivery": float(r["Supplier Delivery Rating"]), "confirmation": float(r["Order Confirmation Rate"]),
               "change": float(r["Order Change Rate"]), "po": float(r[ds.PO]),
               "worst_label": ds.label(worst[sid]), "worst_value": int(r[worst[sid]])}
        if has_lens:
            row["lens_index"] = float(r["Lens_Index"])
        out.append(row)
    return out


@router.post("/suppliers/query")
def query_suppliers(body: QueryIn):
    d = ds.df()
    f = body.filters
    m = (d["Total_Risk_Index"].between(f.tri_min, f.tri_max) &
         (d["Supplier Delivery Rating"] >= f.delivery_min) &
         (d["Order Confirmation Rate"] >= f.confirmation_min) &
         (d["Order Change Rate"] <= f.change_max) &
         d[ds.PO].between(f.po_min, f.po_max))
    if f.levels:
        m &= d["Total_Risk_Index_Level"].isin(f.levels)
    if f.sourcing:
        m &= d["Sourcing Risk Level"].isin(f.sourcing)
    if f.complexity:
        m &= d["Supply Chain Complexity"].isin(f.complexity)
    for key in f.knockout:
        col = ds.resolve_column(key)
        if col:
            m &= d[col] < 75
    if f.max_score < 100:
        m &= d[ds.SCORES].max(axis=1) <= f.max_score
    if f.text:
        sid = ds.resolve(f.text)
        m &= (d.index == sid) if sid else (d["Supplier Name"].str.contains(f.text, case=False, regex=False) |
                                            d.index.str.contains(f.text, case=False, regex=False))
    filtered = d[m]

    weights = ds.normalize_weights(body.lens_weights) if body.lens_weights else None
    if weights:
        filtered = filtered.assign(Lens_Index=ds.lens_index(filtered, weights))
        rank_basis = "Lens_Index"
    else:
        rank_basis = "Total_Risk_Index"

    summary = ds.summary(filtered)
    if weights:  # exact lens average over every match, not just the rows returned
        summary["avg_lens"] = round(float(filtered["Lens_Index"].mean()), 1) if len(filtered) else 0.0

    sort_col = SORT_COLS.get(body.sort) or "Total_Risk_Index"
    if sort_col == "Lens_Index" and not weights:
        sort_col = "Total_Risk_Index"
    filtered = filtered.sort_values(sort_col, ascending=body.ascending)

    limit = max(1, min(int(body.limit or 300), 1000))
    rows = _rows(filtered.head(limit), bool(weights))

    basis = filtered[rank_basis].clip(0, 100) if len(filtered) else pd.Series([], dtype=float)
    bins = np.arange(0, 101, 5)
    counts = np.histogram(basis, bins=bins)[0] if len(basis) else np.zeros(len(bins) - 1, dtype=int)
    histogram = [{"from": int(bins[i]), "to": int(bins[i + 1]), "count": int(counts[i]),
                  "level": ds.level((bins[i] + bins[i + 1]) / 2)} for i in range(len(counts))]

    sample = filtered if len(filtered) <= 600 else filtered.sample(600, random_state=42)
    scatter = [{"id": sid, "tri": float(r["Total_Risk_Index"]), "delivery": float(r["Supplier Delivery Rating"]),
                "level": r["Total_Risk_Index_Level"]} for sid, r in sample.iterrows()]

    # TRI level by sourcing risk: hard-to-replace suppliers skew riskier (mirrors the Streamlit crosstab + caption)
    cross = pd.crosstab(filtered["Sourcing Risk Level"], filtered["Total_Risk_Index_Level"]).reindex(
        index=ds.CAT_ORDER["Sourcing Risk Level"], columns=ds.LEVELS, fill_value=0)
    sourcing_levels = [{"sourcing": sv, **{lv: int(cross.at[sv, lv]) for lv in ds.LEVELS},
                        "avg_tri": round(float(filtered.loc[filtered["Sourcing Risk Level"] == sv, "Total_Risk_Index"].mean()), 1)
                        if int(cross.loc[sv].sum()) else None} for sv in cross.index]

    return jsonable({"total": int(len(filtered)), "summary": summary, "rows": rows, "histogram": histogram,
                      "scatter": scatter, "sourcing_levels": sourcing_levels,
                      "rank_basis": "lens_index" if weights else "tri"})
