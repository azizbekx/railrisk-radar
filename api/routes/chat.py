"""chat page API. Owned by the chat slice.

POST /api/chat streams core.agent.run() over the 10,000-supplier dataset as NDJSON steps
(see api/common.stream_steps). show_chart tool results are enriched here with the real
chart data (values pulled straight from core.dataset) so the frontend never has to guess."""
import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from api import common
from core import agent, dataset as ds

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    question: str
    history: list[ChatMessage] = []
    shortlist: list[str] = []


def _chart(content: dict, title: str) -> dict | None:
    """Build real-data chart payload for a show_chart tool result (see core/agent.py t_show_chart)."""
    kind = content.get("rendered")
    ids = [i for i in (content.get("suppliers") or []) if i in ds.df().index]
    cols = content.get("columns") or []

    if kind == "risk_breakdown":
        if not ids:
            return None
        e = ds.explain(ids[0])
        bars = sorted(e["contributions"], key=lambda p: -abs(p["vs_average"]))
        return {"kind": "risk_breakdown", "title": title or f"Why {ids[0]} has TRI {e['total_risk_index']}",
                "supplier": ids[0], "tri": e["total_risk_index"], "level": e["level"], "average": e["dataset_average_tri"],
                "bars": [{"key": p["score"], "label": p["label"], "value": p["value"], "level": p["level"],
                          "vs_average": p["vs_average"], "weight": p["weight"]} for p in bars]}

    if kind == "compare_bars":
        if not ids:
            return None
        use = [c for c in cols if c not in ds.CATEGORICAL and c != "Supplier Name"][:6] or ["Total_Risk_Index"]
        d = ds.df().loc[ids]
        rows = [{"column": ds.label(c), "key": c, **{sid: float(d.at[sid, c]) for sid in ids}} for c in use]
        names = {sid: d.at[sid, "Supplier Name"] for sid in ids}
        return {"kind": "compare_bars", "title": title or "Comparison", "suppliers": ids, "names": names,
                "columns": [{"key": c, "label": ds.label(c), "isPO": c == ds.PO} for c in use], "rows": rows}

    if kind == "heatmap":
        if not ids:
            return None
        d = ds.df().loc[ids]
        values = {sid: {c: int(d.at[sid, c]) for c in ds.SCORES} for sid in ids}
        tri = {sid: int(d.at[sid, "Total_Risk_Index"]) for sid in ids}
        return {"kind": "heatmap", "title": title or "Risk heatmap", "suppliers": ids,
                "scores": [{"key": c, "label": ds.label(c)} for c in ds.SCORES], "values": values, "tri": tri}

    if kind == "radar":  # rendered as a horizontal dot/bar profile, never a radar chart
        sel = ids[:5]
        if not sel:
            return None
        d = ds.df().loc[sel]
        scores = cols if cols and all(c in ds.SCORES for c in cols) else ds.SCORES
        if len(scores) > 10:  # keep it readable: the 10 scores that differ most across the selection
            scores = list(d[scores].var().sort_values(ascending=False).index[:10])
        values = {sid: {c: int(d.at[sid, c]) for c in scores} for sid in sel}
        return {"kind": "profile", "title": title or "Risk profile", "suppliers": sel,
                "scores": [{"key": c, "label": ds.label(c)} for c in scores], "values": values}

    if kind == "distribution":
        col = ds.resolve_column(cols[0]) if cols else "Total_Risk_Index"
        col = col or "Total_Risk_Index"
        s = ds.df()[col]
        counts, edges = np.histogram(s, bins=30)
        bins = [{"x0": round(float(edges[i]), 1), "x1": round(float(edges[i + 1]), 1), "count": int(counts[i])}
                for i in range(len(counts))]
        marks = [{"id": sid, "value": float(ds.df().at[sid, col])} for sid in ids]
        return {"kind": "distribution", "title": title or f"{ds.label(col)} across 10,000 suppliers",
                "column": col, "label": ds.label(col), "bins": bins, "marks": marks}

    return None


def _enrich(steps):
    """Wrap agent.run()'s step generator, attaching real chart data to show_chart tool_results."""
    last_args: dict = {}
    for s in steps:
        if s.get("type") == "tool_call" and s.get("name") == "show_chart":
            last_args = s.get("args") or {}
        if s.get("type") == "tool_result" and s.get("name") == "show_chart" and isinstance(s.get("content"), dict):
            try:
                s = {**s, "chart": _chart(s["content"], last_args.get("title", ""))}
            except Exception:
                s = {**s, "chart": None}
        yield s


@router.post("/chat")
def chat(body: ChatIn):
    history = [{"role": h.role, "content": h.content} for h in body.history]
    ctx = f"\n\n(Buyer's current shortlist: {', '.join(body.shortlist) if body.shortlist else 'empty'})"
    return common.stream_steps(_enrich(agent.run(body.question + ctx, history, tools=agent.DATA_TOOLS, system=agent.DATA_SYSTEM)))
