"""team page API: the leader + 4 specialist agent team decision. Owned by the team slice."""
from fastapi import APIRouter
from pydantic import BaseModel

from api.common import jsonable, last, lens_weights as resolve_lens, remember, stream
from core import dataset as ds, team

router = APIRouter(prefix="/team")


class RunIn(BaseModel):
    ids: list[str]
    context: str = ""
    lens_name: str = "Dataset TRI (official)"
    lens_weights: dict | None = None


@router.post("/run")
def run(body: RunIn):
    ids = [i for i in body.ids if i in ds.df().index]
    weights = resolve_lens(body.lens_weights)

    def go(log=None):
        res = team.run(ids, body.context, body.lens_name, weights, log=log)
        remember("team", res)
        return res

    return stream(go)


@router.get("/last")
def get_last():
    return jsonable(last("team"))


class ChartIn(BaseModel):
    ids: list[str]
    spec: dict
    area: str | None = None  # restricts columns to this specialist's allowed set


@router.post("/chart")
def chart(body: ChartIn):
    """Real dataset values for a specialist's self-designed chart, so the frontend draws it (no plotly)."""
    ids = [i for i in body.ids if i in ds.df().index]
    allowed = team.chart_columns(body.area) if body.area in team.AGENTS else None
    return jsonable(_chart_data(body.spec, ids, allowed))


def _chart_data(spec: dict, ids: list[str], allowed: list[str] | None) -> dict | None:
    if not isinstance(spec, dict) or not ids:
        return None
    raw = spec.get("columns") or []
    cols = [c for c in (ds.resolve_column(str(x)) for x in (raw if isinstance(raw, list) else [raw])) if c]
    cols = [c for c in dict.fromkeys(cols) if c not in ds.CATEGORICAL and c != "Supplier Name" and (not allowed or c in allowed)]
    if not cols:
        return None
    sel = [s for s in ds.resolve_many(spec.get("suppliers") or [])[0] if s in ids] or list(ids)
    d, mu = ds.df(), ds.means()
    kind = spec.get("kind")
    kind = "dotplot" if kind == "radar" else kind if kind in ("bars", "grouped_bars", "scatter", "heatmap") else "bars"
    out = {
        "kind": kind, "title": spec.get("title") or "",
        "columns": [{"key": c, "label": ds.label(c)} for c in cols],
        "ids": sel, "mean": {c: round(float(mu[c]), 1) for c in cols},
        "rows": [{"id": sid, **{c: round(float(d.at[sid, c]), 1) for c in cols}} for sid in sel],
    }
    if kind == "scatter" and len(cols) >= 2:
        bg = d.sample(min(250, len(d)), random_state=1)
        out["background"] = [{"x": round(float(bg.at[i, cols[0]]), 1), "y": round(float(bg.at[i, cols[1]]), 1)} for i in bg.index]
    return out
