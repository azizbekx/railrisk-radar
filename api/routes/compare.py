"""compare page API. Owned by the compare slice.

POST /api/compare/value: price-vs-risk "best value" ranking from the buyer's own quotes (the dataset has no price column).

POST /api/compare: everything the "Compare shortlist" page needs in one response —
ranking, per-supplier scores (for the heatmap / profile overlay), TRI composition by
risk family, dataset means and best/worst per column.
"""
import math

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


class ValueIn(BaseModel):
    ids: list[str]
    quotes: dict[str, float] = {}
    part_type: str = "standard"
    lens_weights: dict | None = None


def _pts(v: float, lo: float, hi: float) -> float:
    return round((v - lo) / (hi - lo) * 100, 1) if hi > lo else 0.0


def _num(x: float) -> str:
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"


def _pct(f: float) -> str:
    return f"{f * 100:.0f}%" if f >= 0.095 else f"{f * 100:.1f}%"


def _gate_reason(r, spec: dict) -> str | None:
    g = spec["gate"]
    bits = [f"{ds.label(c)[0] + ds.label(c)[1:].lower()} {int(r[c])} ({ds.level(r[c])})" for c in g["scores"] if r[c] >= g["max"]]
    if r["Total_Risk_Index"] >= g["tri_max"]:
        bits.append(f"TRI {int(r['Total_Risk_Index'])} ({ds.level(r['Total_Risk_Index'])})")
    return "; ".join(bits) or None


@router.post("/compare/value")
def compare_value(body: ValueIn):
    part = body.part_type if body.part_type in ds.PART_TYPES else "standard"
    spec = ds.PART_TYPES[part]
    pw = float(spec["price_weight"])
    rw = round(1 - pw, 4)
    use_lens = bool(body.lens_weights)
    ids = [i for i in dict.fromkeys(body.ids) if i in ds.df().index][:MAX_IDS]
    out = {"part_type": part, "label": spec["label"], "price_weight": pw, "risk_weight": rw,
           "risk_label": "Lens index" if use_lens else "TRI", "rows": [], "best": None, "cheapest": None, "safest": None,
           "explanation": "Add at least two suppliers to the shortlist to compare value."}
    if not ids:
        return jsonable(out)

    d = ds.df().loc[ids].copy()
    d["_risk"] = ds.lens_index(d, lens_weights(body.lens_weights)) if use_lens else d["Total_Risk_Index"].astype(float)
    d["_pass"] = ds.part_gate(d, part)
    price = {i: float(body.quotes[i]) for i in ids if i in body.quotes and math.isfinite(body.quotes[i]) and body.quotes[i] > 0}
    q = [i for i in ids if i in price]
    risk = {i: round(float(d.at[i, "_risk"]), 1) for i in ids}
    scored = len(q) >= 2

    if scored:
        r_lo, r_hi = min(risk[i] for i in q), max(risk[i] for i in q)
        p_lo, p_hi = min(price[i] for i in q), max(price[i] for i in q)
    rows = {}
    for i in ids:
        r = d.loc[i]
        ok = bool(r["_pass"])
        lvl = ds.level(risk[i]) if use_lens else r["Total_Risk_Index_Level"]
        x = {"id": i, "name": r["Supplier Name"], "risk": risk[i], "level": lvl, "price": price.get(i), "price_vs_cheapest": None,
             "risk_pts": None, "price_pts": None, "value_score": None, "rank": None, "frontier": False,
             "passes_gate": ok, "gate_reason": None if ok else _gate_reason(r, spec)}
        if i in price:
            x["frontier"] = not any(risk[j] <= risk[i] and price[j] <= price[i] and (risk[j] < risk[i] or price[j] < price[i]) for j in q if j != i)
            if scored:
                x["price_vs_cheapest"] = round(price[i] / p_lo - 1, 4)
                x["risk_pts"], x["price_pts"] = _pts(risk[i], r_lo, r_hi), _pts(price[i], p_lo, p_hi)
                x["value_score"] = round(rw * x["risk_pts"] + pw * x["price_pts"], 1)
        rows[i] = x

    if scored:
        # safety-critical parts never rank a gate failure; other part types rank it but never recommend it
        eligible = sorted((i for i in q if rows[i]["passes_gate"] or part != "safety_critical"),
                          key=lambda i: (rows[i]["value_score"], risk[i], price[i], i))
        for n, i in enumerate(eligible, start=1):
            rows[i]["rank"] = n
        out["best"] = next((i for i in eligible if rows[i]["passes_gate"]), None)
    if q:
        out["cheapest"] = min(q, key=lambda i: (price[i], risk[i], i))
        out["safest"] = min(q, key=lambda i: (risk[i], price[i], i))

    out["rows"] = sorted(rows.values(), key=lambda x: (x["rank"] is None, x["rank"] or 0, x["price"] is None, risk[x["id"]], x["id"]))
    out["explanation"] = _explain(out, rows, price, risk, q, part, spec, rw, pw)
    return jsonable(out)


def _explain(out, rows, price, risk, q, part, spec, rw, pw) -> str:
    kind = spec["label"].lower()
    head = f"For a {kind if kind.endswith('part') else kind + ' part'}, risk counts {rw * 100:.0f}% and price {pw * 100:.0f}%."
    if len(q) < 2:
        return f"{head} Enter quotes from your RFQ for at least two suppliers to rank them by value."
    failing = [i for i in q if not rows[i]["passes_gate"]]
    note = ""
    if failing:
        n = len(failing)
        note = f" {n} quoted supplier{'s' if n > 1 else ''} fail{'' if n > 1 else 's'} the risk gate and {'are' if n > 1 else 'is'} " + (
            "not ranked." if part == "safety_critical" else "flagged and never recommended.")
    best = out["best"]
    if not best:
        return f"{head} No quoted supplier passes the risk gate, so none is recommended."
    cheap, safe = out["cheapest"], out["safest"]
    if best == cheap:
        gap = risk[best] - risk[safe]
        tail = "it is both the cheapest and the safest" if best == safe else (
            f"it is the cheapest, and {_num(gap)} points riskier than the safest ({safe})")
        s = f"{best} is best value: {tail}."
    else:
        more, pts = price[best] / price[cheap] - 1, risk[cheap] - risk[best]
        s = f"{best} is best value: {_pct(more)} more expensive than the cheapest but {_num(pts)} points less risky."
    return f"{head} {s}{note}"
