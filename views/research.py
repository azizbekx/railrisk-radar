"""Research agent: a buyer names a real company, the agent researches it and scores it like the dataset."""
import re

import plotly.graph_objects as go
import streamlit as st

from core import dataset as ds, llm, workflows as wf
from views.common import pill, remember, run_streaming

VERDICT_COLOR = {"approve": "Low", "approve with conditions": "Medium", "escalate": "High", "reject": "Critical"}


def dimension_chart(rep: dict):
    rows = []
    for c in reversed([c for g in ds.GROUPS.values() for c in g]):
        d = (rep.get("scores") or {}).get(c) or {}
        rows.append((ds.label(c), d.get("score"), ds.TRI_WEIGHTS[c]))
    fig = go.Figure(go.Bar(
        y=[f"{l} · {w:.0%}" for l, _, w in rows], x=[v if v is not None else 50 for _, v, _ in rows], orientation="h",
        marker_color=[ds.LEVEL_COLOR[ds.level(v)] if v is not None else "rgba(160,170,165,0.25)" for _, v, _ in rows],
        marker_line=dict(color=["rgba(0,0,0,0)" if v is not None else "#a0aaa5" for _, v, _ in rows], width=1),
        text=[str(v) if v is not None else "no evidence" for _, v, _ in rows], textposition="outside", textangle=0,
        cliponaxis=False))
    for v in (25, 50, 75):
        fig.add_vline(x=v, line_dash="dot", line_color="#b8c2bc")
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=40, b=0), xaxis=dict(range=[0, 100]),
                      title="Scored on the dataset's 18 risk dimensions (grey = no evidence found)")
    return fig


def render():
    st.markdown("Name a **real company**. The agent plans its research, searches news and the web, reads the company's "
                "own site, **digs deeper when it finds red flags**, then scores the company on the same 18 risk "
                "dimensions as your supplier base, with a source link behind every finding.")
    keys = llm.keys_status()
    c = st.columns([3, 1])
    name = c[0].text_input("Company", placeholder="e.g. Knorr-Bremse, Voith, a casting foundry...", key="rs_name",
                           label_visibility="collapsed")
    go_btn = c[1].button("🌐 Research", type="primary", width="stretch",
                         disabled=not (keys["llm"] and keys["tavily"]) or not name)
    if not (keys["llm"] and keys["tavily"]):
        st.caption("Needs an LLM key and TAVILY_API_KEY. Showing the last cached report.")
    if go_btn:
        rep, trace = run_streaming(wf.research_company, name, label=f"Researching {name}", keep=40)
        if rep:
            rep["trace"] = trace
            remember("research", rep)
    rep = st.session_state.get("research")
    if not rep:
        return
    show_report(rep)


def linkify(text: str, src: dict) -> str:
    return re.sub(r"\[(\d+)\]", lambda m: f"[[{m.group(1)}]]({src[int(m.group(1))]['url']})"
                  if int(m.group(1)) in src else m.group(0), text or "")


def show_report(rep: dict):
    src = {s["n"]: s for s in rep.get("sources", [])}

    def cites(ns):
        return " ".join(f"<a href='{src[n]['url']}' target='_blank'>[{n}]</a>" for n in ns or [] if n in src)

    verdict = (rep.get("verdict") or "").lower()
    st.markdown(f"## {rep.get('company', '')} {pill(rep['level'], 'TRI ' + str(rep['total_risk_index']) + ' · ' + rep['level'].upper())} "
                f"{pill(VERDICT_COLOR.get(verdict, 'Medium'), verdict.upper() or 'NO VERDICT')}", unsafe_allow_html=True)
    meta = f"Researched {rep.get('researched_at', '')} · {len(src)} sources"
    if rep.get("website"):
        meta += f" · [{rep['website']}]({rep['website']})"
    st.caption(meta)
    st.markdown(linkify(rep.get("overview", ""), src))
    k = st.columns(4)
    k[0].metric("Total Risk Index (dataset formula)", rep["total_risk_index"], rep["level"], delta_color="off")
    k[1].metric("vs your 10,000 suppliers", f"riskier than {rep['riskier_than_pct']:.0f}%")
    k[2].metric("Evidence coverage", f"{rep['evidence_coverage']:.0%}", help="Share of the TRI weight backed by sources. "
                "Dimensions without evidence count as the dataset average.")
    k[3].metric("Red flags", len(rep.get("red_flags") or []))
    st.info(linkify(rep.get("recommendation", ""), src))

    if rep.get("trace"):
        with st.expander(f"How the agent researched this ({len(rep['trace'])} steps)"):
            st.markdown("\n\n".join(rep["trace"]), unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(dimension_chart(rep), width="stretch")
    with right:
        st.markdown("#### 🚩 Red flags")
        flags = rep.get("red_flags") or []
        if not flags:
            st.success("No red flags found in the sources.")
        for f in flags:
            if not isinstance(f, dict):
                continue
            sev = int(f.get("severity") or 0)
            st.markdown(f"<div class='evt'><b>{f.get('title', '')}</b> · severity {sev}/5 · {f.get('status', '')}<br>"
                        f"{f.get('detail', '')} {cites(f.get('sources'))}</div>", unsafe_allow_html=True)
        if rep.get("strengths"):
            st.markdown("#### ✅ Strengths")
            st.markdown("\n".join(f"- {linkify(s, src)}" for s in rep["strengths"]))

    with st.expander("Evidence per dimension"):
        for c in ds.SCORES:
            d = (rep.get("scores") or {}).get(c) or {}
            if d.get("score") is not None:
                st.markdown(f"**{ds.label(c)}: {d['score']}** · {d.get('evidence', '')} {cites(d.get('sources'))}",
                            unsafe_allow_html=True)
    with st.expander(f"Sources ({len(src)})"):
        st.markdown("\n".join(f"{s['n']}. [{s['title']}]({s['url']}) · *{s.get('area', '')}*" for s in src.values()))
    st.download_button("⬇ Download report (.md)", wf.report_markdown(rep),
                       file_name=f"risk_report_{rep.get('company', 'company').replace(' ', '_')}.md", mime="text/markdown")
