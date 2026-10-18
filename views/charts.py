"""Plotly figures over the supplier dataset. All risk scores: 0 = no risk, 100 = maximum risk."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core import dataset as ds

# Continuous scale that changes hue exactly at the level boundaries 25 / 50 / 75
LEVEL_SCALE = [[0.0, "#2f8a4e"], [0.2499, "#8fbf6a"], [0.25, "#e8d36a"], [0.4999, "#e2b84a"],
               [0.5, "#eda06a"], [0.7499, "#e0794f"], [0.75, "#d65a45"], [1.0, "#a52a1f"]]
PALETTE = ["#1f5f8b", "#c2412d", "#2f8a4e", "#c98a12", "#7a4fa3", "#3a9fb5", "#8a6d4b"]
SCORE_ORDER = [c for g in ds.GROUPS.values() for c in g]


def _short(sid: str) -> str:
    return sid.replace("SUPP_", "S")


def _layout(fig, height, title="", **kw):
    fig.update_layout(height=height, title=title, margin=dict(l=0, r=0, t=40 if title else 10, b=0), **kw)
    return fig


def breakdown(sid: str, height: int = 420):
    """Waterfall: dataset average TRI → each score's contribution vs average → this supplier's TRI."""
    e = ds.explain(sid)
    parts = sorted(e["contributions"], key=lambda p: -abs(p["vs_average"]))
    big, rest = parts[:10], parts[10:]
    x = ["Dataset average"] + [f"{p['label']} ({p['value']})" for p in big] + ["Other 8 scores", f"{sid} TRI"]
    y = [e["dataset_average_tri"]] + [p["vs_average"] for p in big] + [sum(p["vs_average"] for p in rest), 0]
    fig = go.Figure(go.Waterfall(
        orientation="v", x=x, y=y, measure=["absolute"] + ["relative"] * (len(big) + 1) + ["total"],
        text=[f"{e['dataset_average_tri']:.0f}"] + [f"{v:+.1f}" for v in y[1:-1]] + [str(e["total_risk_index"])],
        textposition="outside", increasing=dict(marker_color="#c2412d"), decreasing=dict(marker_color="#2f8a4e"),
        totals=dict(marker_color=ds.LEVEL_COLOR[e["level"]]), connector=dict(line=dict(color="#c9d1cc"))))
    lo = min(np.cumsum(y[:-1]).min(), e["dataset_average_tri"]) - 8
    hi = max(np.cumsum(y[:-1]).max(), e["total_risk_index"]) + 8
    return _layout(fig, height, f"Why {sid} has TRI {e['total_risk_index']}: points vs the dataset average",
                   yaxis=dict(range=[max(0, lo), min(100, hi)], title="Total Risk Index"), xaxis=dict(tickangle=-35),
                   showlegend=False)


def score_bars(sid: str, height: int = 470):
    """Each score with its level color, weight and how many suppliers it is riskier than."""
    e = ds.explain(sid)
    by = {p["score"]: p for p in e["contributions"]}
    rows = [by[c] for c in SCORE_ORDER][::-1]
    fig = go.Figure(go.Bar(
        y=[f"{p['label']} · {p['weight']:.0%}" for p in rows], x=[p["value"] for p in rows], orientation="h",
        marker_color=[ds.LEVEL_COLOR[p["level"]] for p in rows],
        text=[f"{p['value']} · riskier than {p['riskier_than_pct']:.0f}%" for p in rows], textposition="auto",
        hovertemplate="%{y}: %{x}<extra></extra>"))
    for v in (25, 50, 75):
        fig.add_vline(x=v, line_dash="dot", line_color="#b8c2bc")
    return _layout(fig, height, "Risk scores (weight in TRI) and percentile", xaxis=dict(range=[0, 100]))


def heatmap(ids: list[str], order: list[str] | None = None, height: int | None = None):
    d = ds.df().loc[order or ids]
    cols = ["Total_Risk_Index"] + SCORE_ORDER
    z = d[cols].values
    fig = go.Figure(go.Heatmap(
        z=z, x=["TRI"] + [ds.label(c) for c in SCORE_ORDER], y=[f"{s} " for s in d.index], zmin=0, zmax=100,
        colorscale=LEVEL_SCALE, text=z, texttemplate="%{text}", textfont=dict(size=11), xgap=2, ygap=2,
        colorbar=dict(title="risk", tickvals=[0, 25, 50, 75, 100], len=0.8),
        hovertemplate="%{y} · %{x}: %{z}<extra></extra>"))
    # group separators
    pos = 0.5
    for g in list(ds.GROUPS.values())[:-1]:
        pos += len(g)
        fig.add_vline(x=pos, line_color="white", line_width=4)
    fig = _layout(fig, height or max(300, 170 + 30 * len(d)), "", xaxis=dict(side="top", tickangle=-40),
                  yaxis=dict(autorange="reversed"))
    fig.update_layout(margin=dict(l=0, r=0, t=130, b=0))
    return fig


def stacked_tri(ids: list[str], order: list[str] | None = None, height: int | None = None):
    """TRI composition per supplier by score family: shows *where* each supplier's risk comes from."""
    d = ds.df().loc[order or ids]
    fig = go.Figure()
    for (g, cols), col in zip(ds.GROUPS.items(), PALETTE):
        pts = sum(d[c] * ds.TRI_WEIGHTS[c] for c in cols)
        fig.add_bar(y=list(d.index), x=pts, name=g, orientation="h", marker_color=col,
                    hovertemplate="%{y} · " + g + ": %{x:.1f} pts<extra></extra>")
    fig.add_scatter(y=list(d.index), x=d["Total_Risk_Index"] + 2, mode="text", text=d["Total_Risk_Index"].astype(str),
                    showlegend=False, textposition="middle right", hoverinfo="skip")
    return _layout(fig, height or max(320, 170 + 28 * len(d)), "Where each TRI comes from (weighted points by risk family)",
                   barmode="stack", yaxis=dict(autorange="reversed"), xaxis=dict(range=[0, 100]),
                   legend=dict(orientation="h", y=-0.08, yanchor="top", font_size=11))


def radar(ids: list[str], height: int = 460):
    d = ds.df().loc[ids[:6]]
    theta = [ds.label(c) for c in SCORE_ORDER]
    fig = go.Figure()
    for (sid, r), col in zip(d.iterrows(), PALETTE):
        fig.add_scatterpolar(r=list(r[SCORE_ORDER]) + [r[SCORE_ORDER[0]]], theta=theta + [theta[0]], name=f"{sid} (TRI {r['Total_Risk_Index']})",
                             line=dict(color=col, width=2), fill="toself", opacity=0.55)
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], tickvals=[25, 50, 75], tickfont_size=9),
                                 angularaxis=dict(tickfont_size=10)))
    return _layout(fig, height, "Risk profile (further out = riskier)", legend=dict(orientation="h", y=-0.1))


def head_to_head(a: str, b: str, height: int = 470):
    """Diverging bars: score of A minus score of B. Left (green) = A is safer."""
    d = ds.df()
    diff = [(ds.label(c), int(d.at[a, c]) - int(d.at[b, c]), ds.TRI_WEIGHTS[c]) for c in SCORE_ORDER][::-1]
    fig = go.Figure(go.Bar(y=[f"{l} · {w:.0%}" for l, _, w in diff], x=[v for _, v, _ in diff], orientation="h",
                           marker_color=["#2f8a4e" if v < 0 else "#c2412d" if v > 0 else "#b8c2bc" for _, v, _ in diff],
                           text=[f"{v:+d}" for _, v, _ in diff], textposition="outside"))
    fig.add_vline(x=0, line_color="#6b7a73")
    m = max(10, max(abs(v) for _, v, _ in diff) + 10)
    return _layout(fig, height, f"{a} minus {b} (green = {a} is safer)", xaxis=dict(range=[-m, m]))


def compare_bars(ids: list[str], columns: list[str], height: int = 380):
    cols = [c for c in (ds.resolve_column(x) for x in columns) if c and c not in ds.CATEGORICAL][:6] or ["Total_Risk_Index"]
    d = ds.df().loc[ids]
    fig = go.Figure()
    for sid, col in zip(d.index, PALETTE * 4):
        fig.add_bar(x=[ds.label(c) for c in cols], y=[d.at[sid, c] for c in cols], name=sid, marker_color=col,
                    text=[f"{d.at[sid, c]:.0f}" if c != ds.PO else f"€{d.at[sid, c]/1e6:.1f}M" for c in cols],
                    textposition="outside")
    return _layout(fig, height, "", barmode="group", legend=dict(orientation="h", y=1.12))


def distribution(column: str, ids: list[str] | None = None, height: int = 330):
    col = ds.resolve_column(column) or "Total_Risk_Index"
    s = ds.df()[col]
    fig = go.Figure(go.Histogram(x=s, nbinsx=50, marker_color="#c9d6cf", name="all suppliers"))
    for sid, c in zip(ids or [], PALETTE * 4):
        v = ds.df().at[sid, col]
        fig.add_vline(x=v, line_color=c, line_width=2, annotation_text=f"{_short(sid)} {v:.0f}", annotation_font_color=c)
    return _layout(fig, height, f"{ds.label(col)} across 10,000 suppliers", showlegend=False, bargap=0.05)


def landscape(d: pd.DataFrame, highlight: list[str], index_col: str = "Total_Risk_Index", height: int = 380):
    """Risk vs delivery performance for the filtered set; the shortlist is highlighted."""
    sample = d if len(d) <= 4000 else d.sample(4000, random_state=1)
    fig = go.Figure()
    for lvl in ds.LEVELS:
        s = sample[sample["Total_Risk_Index_Level"] == lvl]
        fig.add_scattergl(x=s[index_col], y=s["Supplier Delivery Rating"], mode="markers", name=lvl,
                          marker=dict(size=5, color=ds.LEVEL_COLOR[lvl], opacity=0.45),
                          text=s.index, hovertemplate="%{text}<br>risk %{x}<br>delivery %{y:.1f}%<extra></extra>")
    h = ds.df().loc[[i for i in highlight if i in ds.df().index]]
    if len(h):
        hx = h[index_col] if index_col in h else h["Total_Risk_Index"]
        fig.add_scatter(x=hx, y=h["Supplier Delivery Rating"], mode="markers+text", name="shortlist",
                        marker=dict(size=13, color="rgba(0,0,0,0)", line=dict(color="#1b2420", width=2)),
                        text=[_short(i) for i in h.index], textposition="top center", textfont_size=10)
    return _layout(fig, height, "Risk vs delivery performance (top-left = safe and reliable)",
                   xaxis=dict(title="risk index"), yaxis=dict(title="delivery rating %"),
                   legend=dict(orientation="h", y=-0.2))


def from_spec(spec: dict):
    """Render a chart the chatbot asked for via the show_chart tool."""
    kind, ids, cols = spec.get("rendered"), spec.get("suppliers", []), spec.get("columns", [])
    if kind == "risk_breakdown" and ids:
        return breakdown(ids[0], height=380)
    if kind == "heatmap" and ids:
        return heatmap(ids)
    if kind == "radar" and ids:
        return radar(ids, height=420)
    if kind == "compare_bars" and ids:
        return compare_bars(ids, cols or ["Total_Risk_Index"])
    if kind == "distribution":
        return distribution(cols[0] if cols else "Total_Risk_Index", ids)
    return None
