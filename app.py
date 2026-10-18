"""RailRisk Radar: agentic supplier risk intelligence for rolling stock."""
import queue
import threading
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import agent, llm, model as m, workflows as wf

st.set_page_config(page_title="RailRisk Radar", page_icon="🚆", layout="wide")

BAND_COLOR = {"low": "#2f8a4e", "watch": "#c98a12", "act now": "#c2412d"}
ACCENT = "#1f5f8b"

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem;}
.pill {display:inline-block;padding:2px 10px;border-radius:99px;font-size:0.8rem;font-weight:600;color:white}
.trace {font-family: ui-monospace, Menlo, monospace; font-size: 0.82rem; line-height:1.5}
.evt {border-left: 3px solid #c98a12; padding: 6px 12px; margin: 6px 0; background: rgba(127,127,127,0.06); border-radius: 0 6px 6px 0}
.muted {color: #6b7a73; font-size: 0.86rem}
div[data-testid="stMetricValue"] {font-size: 1.7rem}
</style>
""", unsafe_allow_html=True)


def pill(band: str, text: str | None = None) -> str:
    return f'<span class="pill" style="background:{BAND_COLOR[band]}">{text or band.upper()}</span>'


def eur(x: float) -> str:
    return f"€{x/1e6:.1f}M" if abs(x) >= 1e6 else f"€{x/1e3:.0f}k"


def trace_line(step: dict) -> str:
    t = step["type"]
    who = f"[{step['supplier']}] " if step.get("supplier") else ""
    if t == "tool_call":
        args = ", ".join(f"{k}={v!r}" for k, v in step.get("args", {}).items())
        return f"🔧 {who}`{step['name']}`({args})"
    if t == "tool_result":
        c = step["content"]
        if not isinstance(c, str):
            n = len(c) if isinstance(c, list) else len(c.keys()) if isinstance(c, dict) else 0
            c = f"{n} items returned"
        return f"↳ {who}{c}"
    if t == "thought":
        return f"💭 {step['content']}"
    if t == "error":
        return f"⚠️ {step['content']}"
    return step.get("content", "")


def run_streaming(fn, *args, label="Agent working", **kwargs):
    """Run fn(log=..., ...) in a thread and stream its log into a status box."""
    q, out = queue.Queue(), {}

    def target():
        try:
            out["result"] = fn(*args, log=q.put, **kwargs)
        except Exception as e:
            out["error"] = e

    th = threading.Thread(target=target, daemon=True)
    th.start()
    lines = []
    with st.status(label, expanded=True) as status:
        box = st.empty()
        while th.is_alive() or not q.empty():
            try:
                lines.append(trace_line(q.get(timeout=0.3)))
                box.markdown("\n\n".join(lines[-14:]))
            except queue.Empty:
                pass
        if "error" in out:
            status.update(label=f"Failed: {out['error']}", state="error")
            return None, lines
        status.update(label=f"{label}: done ({len(lines)} steps)", state="complete", expanded=False)
    return out.get("result"), lines


def sankey(edges: list[tuple], title: str = "", height: int = 420):
    labels = []
    for a, b, _ in edges:
        for n in (a, b):
            if n not in labels:
                labels.append(n)
    proj_names = {p["name"] for p in m.projects().values()}
    sup_names = {s["name"] for s in m.suppliers().values()}
    colors = ["#c2412d" if l in sup_names else ACCENT if l in proj_names else "#8a9a92" for l in labels]
    seen = set()
    src, tgt, val = [], [], []
    for a, b, v in edges:
        if (a, b) in seen:
            continue
        seen.add((a, b))
        src.append(labels.index(a)); tgt.append(labels.index(b)); val.append(v)
    fig = go.Figure(go.Sankey(
        node=dict(label=labels, color=colors, pad=14, thickness=14),
        link=dict(source=src, target=tgt, value=val, color="rgba(194,65,45,0.18)")))
    fig.update_layout(title=title, height=height, margin=dict(l=10, r=10, t=40 if title else 10, b=10), font_size=12)
    return fig


# ---------- sidebar ----------

with st.sidebar:
    st.markdown("## 🚆 RailRisk Radar")
    st.caption("Agentic supplier risk intelligence for rolling stock")
    keys = llm.keys_status()
    st.markdown(f"Nemotron (Token Factory): {'🟢' if keys['nebius'] else '🔴 set NEBIUS_API_KEY'}  \n"
                f"Tavily search: {'🟢' if keys['tavily'] else '🔴 set TAVILY_API_KEY'}")
    models = llm.nemotron_models() if keys["nebius"] else []
    if models:
        default = llm.model()
        choice = st.selectbox("Model", models, index=models.index(default) if default in models else 0)
        llm.MODEL["name"] = choice
    else:
        st.caption(f"Model: `{llm.model()}`")
    ev = agent.load_events()
    st.divider()
    st.markdown(f"**Agent scan cache:** {len(ev)} suppliers scanned")
    if ev:
        st.caption("Last scan: " + max(v.get("scanned_at", "") for v in ev.values()))
    st.caption("Supplier and customer names are fictional. News signals are live.")

scores = agent.current_scores()
score_by_id = {r["id"]: r for r in scores}
summary = m.portfolio_summary(scores)

st.title("Supplier Risk Radar")
st.caption(f"Siemens Mobility rolling stock · {len(m.projects())} train projects · {summary['suppliers']} suppliers (tier 1 and tier 2) · as of {m.TODAY:%d %b %Y}")

tab_over, tab_deep, tab_what, tab_chat, tab_dd = st.tabs(
    ["📡 Overview", "🔍 Supplier deep dive", "🌪️ What-if scenario", "💬 Risk copilot", "🧾 Live due diligence"])

# ---------- overview ----------

with tab_over:
    c = st.columns(5)
    c[0].metric("Suppliers monitored", summary["suppliers"])
    c[1].metric("Act now (≥70)", summary["act"])
    c[2].metric("Watch (40–69)", summary["watch"])
    c[3].metric("Single-source suppliers", summary["single_source"])
    c[4].metric("€ at risk (6-week outage, flagged)", eur(summary["exposure_eur"]))

    left, right = st.columns([3, 2])
    with left:
        sup = m.suppliers()
        fig = go.Figure()
        for s in sup.values():
            for t1 in s["feeds"]:
                d = sup[t1]
                fig.add_trace(go.Scattermap(lat=[s["lat"], d["lat"]], lon=[s["lon"], d["lon"]], mode="lines",
                                            line=dict(width=1, color="rgba(31,95,139,0.35)"), hoverinfo="skip", showlegend=False))
        df_map = pd.DataFrame([{**s, "score": score_by_id[s["id"]]["score"], "band": score_by_id[s["id"]]["band"]} for s in sup.values()])
        for b in ["low", "watch", "act now"]:
            d = df_map[df_map.band == b]
            fig.add_trace(go.Scattermap(
                lat=d.lat, lon=d.lon, mode="markers", name=b,
                marker=dict(size=10 + d.score / 5, color=BAND_COLOR[b], opacity=0.85),
                text=d.name + "<br>" + d.category + "<br>Risk " + d.score.astype(str),
                hoverinfo="text"))
        fig.update_layout(map=dict(style="carto-positron", center=dict(lat=45, lon=20), zoom=2.3),
                          height=470, margin=dict(l=0, r=0, t=0, b=0),
                          legend=dict(orientation="h", y=0.02, x=0.01, bgcolor="rgba(255,255,255,0.7)"))
        st.plotly_chart(fig, width="stretch")
    with right:
        top = scores[:10]
        fig = go.Figure()
        palette = ["#c2412d", "#e0794f", "#1f5f8b", "#6b8fb0", "#c98a12", "#8a9a92", "#4f7a5e"]
        for (k, w), col in zip(m.WEIGHTS.items(), palette):
            fig.add_bar(y=[m.suppliers()[r["id"]]["name"][:26] for r in top], x=[r["factors"][k] * w for r in top],
                        name=m.FACTOR_LABELS[k], orientation="h", marker_color=col)
        fig.update_layout(barmode="stack", height=470, margin=dict(l=0, r=0, t=30, b=0), title="Top 10 risk scores by factor",
                          yaxis=dict(autorange="reversed"), legend=dict(orientation="h", y=-0.15, font_size=10),
                          xaxis=dict(range=[0, 100], title="risk score"))
        st.plotly_chart(fig, width="stretch")

    st.subheader("Watch list")
    rows = []
    for r in scores:
        s = m.suppliers()[r["id"]]
        rows.append({"ID": r["id"], "Supplier": s["name"], "Country": s["country"], "Makes": s["category"],
                     "Tier": s["tier"], "Risk": r["score"], "Band": r["band"],
                     "Agent events": len(agent.events_for(r["id"])), "Why": "; ".join(r["reasons"][:3])})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=330,
                 column_config={"Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%.0f")})

    st.subheader("Agent risk scan")
    st.caption("Nemotron searches live news per supplier region, industry and raw material, then extracts cited risk events.")
    default_ids = [r["id"] for r in scores[:8]]
    pick = st.multiselect("Suppliers to scan", options=list(m.suppliers()), default=default_ids,
                          format_func=lambda i: f"{i} · {m.suppliers()[i]['name']}")
    if st.button("▶ Run agent scan", type="primary", disabled=not (keys["nebius"] and keys["tavily"]) or not pick):
        res, _ = run_streaming(wf.scan_many, pick, label=f"Scanning {len(pick)} suppliers")
        if res is not None:
            st.success("Scan complete. Scores updated.")
            time.sleep(0.6)
            st.rerun()

# ---------- deep dive ----------

with tab_deep:
    ids = [r["id"] for r in scores]
    sid = st.selectbox("Supplier", ids, format_func=lambda i: f"{m.suppliers()[i]['name']}  ·  risk {score_by_id[i]['score']:.0f}")
    s, r = m.suppliers()[sid], score_by_id[sid]
    head, gauge = st.columns([3, 1])
    with head:
        st.markdown(f"### {s['name']} {pill(r['band'])}", unsafe_allow_html=True)
        comps = ", ".join(c["component"] for c in m.components_of(sid)) or f"Tier 2 → feeds {', '.join(m.suppliers()[x]['name'] for x in s['feeds'])}"
        st.markdown(f"{s['city']}, {m.country_risk()[s['country']]['name']} · **{s['category']}** · {comps}")
        if s["note"]:
            st.caption(s["note"])
        st.markdown("**Why this score:** " + ("; ".join(r["reasons"]) or "no major issues"))
    with gauge:
        g = go.Figure(go.Indicator(mode="gauge+number", value=r["score"], number=dict(suffix="/100"),
                                   gauge=dict(axis=dict(range=[0, 100]), bar=dict(color=BAND_COLOR[r["band"]]),
                                              steps=[dict(range=[0, 40], color="#e8f1ea"), dict(range=[40, 70], color="#f7edd8"),
                                                     dict(range=[70, 100], color="#f6dfd9")])))
        g.update_layout(height=170, margin=dict(l=10, r=10, t=10, b=0))
        st.plotly_chart(g, width="stretch")

    a, b, c3 = st.columns(3)
    with a:
        f = r["factors"]
        fig = go.Figure(go.Bar(y=[m.FACTOR_LABELS[k] for k in f], x=list(f.values()), orientation="h",
                               marker_color=[BAND_COLOR[m.band(v)] for v in f.values()],
                               text=[f"{v:.0f} × {m.WEIGHTS[k]:.0%}" for k, v in f.items()], textposition="auto"))
        fig.update_layout(height=290, margin=dict(l=0, r=0, t=30, b=0), title="Factor scores (0–100) × weight",
                          xaxis=dict(range=[0, 100]), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
    with b:
        months = pd.date_range(end="2026-09-30", periods=6, freq="ME").strftime("%b")
        fig = go.Figure(go.Scatter(x=list(months), y=s["otd_6m"], mode="lines+markers", line=dict(color=ACCENT, width=3), fill="tozeroy",
                                   fillcolor="rgba(31,95,139,0.08)"))
        fig.add_hline(y=95, line_dash="dot", line_color="#8a9a92", annotation_text="target 95%")
        fig.update_layout(height=290, margin=dict(l=0, r=0, t=30, b=0), title="On-time delivery %", yaxis=dict(range=[70, 100]))
        st.plotly_chart(fig, width="stretch")
    with c3:
        st.markdown("**Certificates**")
        icon = {"valid": "🟢", "expiring": "🟠", "expired": "🔴", "missing": "🔴"}
        st.dataframe(pd.DataFrame([{"": icon[x["status"]], "Certificate": x["cert"], "Expiry": x["expiry"] or "—",
                                    "Days left": x["days_left"]} for x in r["certs"]]), hide_index=True, width="stretch")
        st.markdown(f"<span class='muted'>Spend €{s['spend_meur']}M/yr · quality {s['quality_ppm']} PPM · {s['ncr_12m']} NCRs (12m) · "
                    f"financial health {s['financial_score']}/100 · stock cover {s['stock_days']} days · lead time {s['lead_time_weeks']} wks</span>",
                    unsafe_allow_html=True)

    st.markdown("#### Agent-found risk events")
    sev = agent.load_events().get(sid)
    if not sev:
        st.info("Not scanned yet. Run the agent scan from the Overview tab.")
    else:
        st.caption(f"{sev.get('summary', '')}  ·  {sev.get('sources', 0)} articles read · scanned {sev.get('scanned_at', '')}")
        for e in sev.get("events", []):
            st.markdown(f"<div class='evt'><b>{e.get('title', '')}</b> · {e.get('type', '')} · severity {e.get('severity')}/5 · "
                        f"confidence {float(e.get('confidence', 0)):.0%}<br>{e.get('summary', '')}<br>"
                        f"<a href='{e.get('url', '')}' target='_blank'>{e.get('url', '')[:90]}</a></div>", unsafe_allow_html=True)
        if not sev.get("events"):
            st.success("No relevant risk events found in recent news.")

    st.markdown("#### Impact if this supplier is disrupted")
    w1, w2 = st.columns([1, 1])
    weeks = w1.slider("Outage length (weeks)", 1, 16, 6, key="dd_weeks")
    loss = w2.slider("Capacity lost", 0.1, 1.0, 1.0, 0.1, key="dd_loss")
    imp = m.trace_impact(sid, weeks, loss)
    k1, k2, k3 = st.columns(3)
    k1.metric("€ penalty exposure", eur(imp["total_exposure_eur"]))
    k2.metric("Projects late", sum(1 for p in imp["projects"] if p["late_days"] > 0))
    k3.metric("Worst delay", f"{max([p['late_days'] for p in imp['projects']] or [0])} days")
    st.plotly_chart(sankey(imp["edges"], height=300), width="stretch")
    st.dataframe(pd.DataFrame(imp["projects"]).rename(columns={"exposure_eur": "exposure €"}), hide_index=True, width="stretch")

    if st.button("🛠 Generate mitigation plan", disabled=not keys["nebius"]):
        with st.spinner("Nemotron is drafting a mitigation plan..."):
            try:
                st.session_state[f"mit_{sid}"] = wf.mitigation(sid, weeks)
            except Exception as e:
                st.error(f"Mitigation failed: {e}")
    plan = st.session_state.get(f"mit_{sid}")
    if plan:
        st.markdown(f"**{plan.get('headline', '')}**")
        st.dataframe(pd.DataFrame(plan.get("actions", [])), hide_index=True, width="stretch")
        alts = m.find_alternatives(m.components_of(sid)[0]["component"] if m.components_of(sid) else s["category"])
        if alts:
            st.markdown("**Alternative sources on file**")
            st.dataframe(pd.DataFrame(alts), hide_index=True, width="stretch")
        em = plan.get("email", {})
        if em:
            with st.expander(f"✉️ Draft email: {em.get('subject', '')}", expanded=True):
                st.markdown(f"**To:** {em.get('to', '')}  \n**Subject:** {em.get('subject', '')}")
                st.text(em.get("body", ""))

# ---------- what-if ----------

EXAMPLES = [
    "Severe flooding in Penang, Malaysia shuts semiconductor plants for 5 weeks",
    "China suspends export licences for rare earth magnets for 3 months",
    "Nationwide strike in the Czech steel and foundry industry",
    "Magnitude 7 earthquake near Bursa, Turkey",
]

with tab_what:
    st.markdown("Describe any disruption. Nemotron maps it to affected suppliers, then the supply graph traces it to trains and euros.")
    cols = st.columns(len(EXAMPLES))
    for col, ex in zip(cols, EXAMPLES):
        if col.button(ex, width="stretch"):
            st.session_state["scenario_text"] = ex
    text = st.text_area("Scenario", key="scenario_text", height=80, placeholder="e.g. Port of Rotterdam closed by a cyber attack for 2 weeks")
    if st.button("🌪️ Simulate impact", type="primary", disabled=not keys["nebius"] or not text):
        with st.spinner("Mapping the scenario onto the supplier base..."):
            try:
                st.session_state["scenario"] = wf.scenario(text)
            except Exception as e:
                st.error(f"Scenario failed: {e}")
    sc = st.session_state.get("scenario")
    if sc:
        st.markdown(f"### {sc.get('title', '')}")
        st.caption(f"{sc.get('type', '')} · {sc.get('location', '')} · {sc.get('duration_weeks', '?')} weeks · {sc.get('explanation', '')}")
        k = st.columns(4)
        k[0].metric("Suppliers hit", len(sc["impacts"]))
        k[1].metric("Train projects late", sum(1 for p in sc["projects"] if p["late_days"] > 0))
        k[2].metric("Worst delay", f"{max([p['late_days'] for p in sc['projects']] or [0])} days")
        k[3].metric("€ penalty exposure", eur(sc["total_exposure_eur"]))
        edges = []
        for imp in sc["impacts"]:
            edges.append(("⚡ " + (sc.get("title") or "Event")[:40], imp["supplier"], 1))
            edges += imp["edges"]
        if edges:
            st.plotly_chart(sankey(edges, "Impact cascade: event → suppliers → components → trains", height=460), width="stretch")
        hit = pd.DataFrame([{"Supplier": i["supplier"], "Why hit": i["reason"], "Capacity lost": f"{i['capacity_loss']:.0%}",
                             "Exposure": eur(i["total_exposure_eur"])} for i in sc["impacts"]])
        if len(hit):
            st.dataframe(hit, hide_index=True, width="stretch")
        if sc["projects"]:
            st.dataframe(pd.DataFrame(sc["projects"]).rename(columns={"exposure_eur": "exposure €"}), hide_index=True, width="stretch")
        if sc.get("lat") is not None and sc["impacts"]:
            mf = go.Figure()
            mf.add_trace(go.Scattermap(lat=[sc["lat"]], lon=[sc["lon"]], mode="markers", marker=dict(size=34, color="rgba(194,65,45,0.35)"),
                                       name="event", text=[sc.get("title", "")], hoverinfo="text"))
            hs = [m.suppliers()[i["supplier_id"]] for i in sc["impacts"]]
            mf.add_trace(go.Scattermap(lat=[h["lat"] for h in hs], lon=[h["lon"] for h in hs], mode="markers+text",
                                       marker=dict(size=12, color="#c2412d"), text=[h["name"] for h in hs], textposition="top right",
                                       name="suppliers hit"))
            mf.update_layout(map=dict(style="carto-positron", center=dict(lat=float(sc["lat"]), lon=float(sc["lon"])), zoom=2.5),
                             height=320, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
            st.plotly_chart(mf, width="stretch")

# ---------- copilot ----------

with tab_chat:
    st.markdown("Ask anything about the supplier base. The agent calls tools: supplier data, live news, impact tracing, alternatives.")
    if "chat" not in st.session_state:
        st.session_state.chat = []
    qs = ["Which single-sourced suppliers in high-risk countries threaten Mireo Plus H?",
          "What happens to our trains if Bohemia Steel Castings goes insolvent next month?",
          "Check the latest news on rare earth export controls and tell me which suppliers are exposed."]
    qc = st.columns(len(qs))
    preset = None
    for col, q in zip(qc, qs):
        if col.button(q, width="stretch"):
            preset = q
    for msg in st.session_state.chat:
        with st.chat_message(msg["role"]):
            if msg.get("trace"):
                with st.expander(f"Agent trace ({len(msg['trace'])} steps)"):
                    st.markdown("\n\n".join(msg["trace"]))
            st.markdown(msg["content"])
    prompt = st.chat_input("Ask the risk copilot...", disabled=not keys["nebius"]) or preset
    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)
        history = [{"role": x["role"], "content": x["content"]} for x in st.session_state.chat[-6:]]
        st.session_state.chat.append({"role": "user", "content": prompt})
        with st.chat_message("assistant"):
            trace, answer = [], ""
            with st.status("Agent reasoning", expanded=True) as status:
                for step in agent.run(prompt, history):
                    if step["type"] == "answer":
                        answer = step["content"]
                    else:
                        trace.append(trace_line(step))
                        st.markdown(trace[-1])
                status.update(label=f"Agent trace ({len(trace)} steps)", state="complete", expanded=False)
            st.markdown(answer)
        st.session_state.chat.append({"role": "assistant", "content": answer, "trace": trace})

# ---------- due diligence ----------

with tab_dd:
    st.markdown("Run live due diligence on **any real company** before onboarding it as a supplier. "
                "The agent searches the web, plans follow-up research, and writes a cited report.")
    name = st.text_input("Company name", placeholder="e.g. a brake, bogie or semiconductor supplier", key="dd_name")
    if st.button("🧾 Run due diligence", type="primary", disabled=not (keys["nebius"] and keys["tavily"]) or not name):
        rep, _ = run_streaming(wf.due_diligence, name, label=f"Researching {name}")
        if rep:
            st.session_state["dd"] = rep
    rep = st.session_state.get("dd")
    if rep:
        bnd = rep.get("band", "watch") if rep.get("band") in BAND_COLOR else m.band(float(rep.get("score", 50)))
        st.markdown(f"### {rep.get('company', '')} {pill(bnd, f'RISK {rep.get('score', '?')}/100')}", unsafe_allow_html=True)
        st.markdown(rep.get("overview", ""))
        fac = rep.get("factors", [])
        if fac:
            st.dataframe(pd.DataFrame([{"Factor": f.get("name"), "Risk": f.get("score"), "Finding": f.get("finding"),
                                        "Sources": " ".join(f.get("sources", [])[:2])} for f in fac]),
                         hide_index=True, width="stretch",
                         column_config={"Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%d"),
                                        "Sources": st.column_config.TextColumn(width="medium")})
        if rep.get("red_flags"):
            st.markdown("**Red flags**\n" + "\n".join(f"- {x}" for x in rep["red_flags"]))
        st.info(rep.get("recommendation", ""))
        st.caption(f"Based on {rep.get('source_count', 0)} web sources.")
