"""Rail impact lab: the original RailRisk Radar demo. 32 rolling-stock suppliers wired to a bill of materials and
4 train projects, live news scanning, what-if disruption simulation and a rail copilot. Fictional data."""
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import agent, model as m, workflows as wf
from core.fmt import eur, trace_line
from views.common import ACCENT, BAND_COLOR, pill, remember, run_streaming


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


EXAMPLES = [
    "Severe flooding in Penang, Malaysia shuts semiconductor plants for 5 weeks",
    "China suspends export licences for rare earth magnets for 3 months",
    "Nationwide strike in the Czech steel and foundry industry",
    "Magnitude 7 earthquake near Bursa, Turkey",
]


def delivery_timeline(projects: list[dict]):
    """Baseline delivery vs slipped delivery per train project."""
    today = pd.Timestamp(m.TODAY)
    fig = go.Figure()
    rows = sorted(projects, key=lambda p: p["delivery"])
    names = [f"{p['name']}" for p in rows]
    base = [pd.Timestamp(p["delivery"]) for p in rows]
    fig.add_bar(y=names, x=[(b - today).days * 86400000 for b in base], base=[today] * len(rows), orientation="h",
                marker_color="#c9d6cf", name="On plan", hovertemplate="%{y}: due %{customdata}<extra></extra>",
                customdata=[p["delivery"] for p in rows])
    fig.add_bar(y=names, x=[p["late_days"] * 86400000 for p in rows], base=base, orientation="h",
                marker_color="#c2412d", name="Slip", text=[f"+{p['late_days']} d · {eur(p['exposure_eur'])}" if p["late_days"] else "" for p in rows],
                textposition="outside", hovertemplate="%{y}: +%{text}<extra></extra>")
    fig.update_layout(barmode="overlay", height=60 + 52 * len(rows), margin=dict(l=0, r=90, t=34, b=0),
                      title="Delivery slip per train project", xaxis=dict(type="date"), legend=dict(orientation="h", y=1.12, x=0.6))
    return fig


def render(keys: dict):
    """Nested tabs for the rail lab; keys = llm.keys_status()."""
    scores = agent.current_scores()
    score_by_id = {r["id"]: r for r in scores}
    summary = m.portfolio_summary(scores)
    llm_name = "Claude" if keys["provider"] == "claude" else "Nemotron"

    st.markdown("### 🚆 Rail impact lab")
    st.caption(f"Siemens Mobility rolling stock · {len(m.projects())} train projects · {summary['suppliers']} suppliers (tier 1 and tier 2) · as of {m.TODAY:%d %b %Y}")
    st.info("Rail extension: how a single supplier failure cascades through a train bill of materials into delivery delays and contract penalties. "
            "Uses a separate, fictional 32-supplier rail dataset; the buyer tabs use the 10,000-supplier Siemens dataset.")
    tab_over, tab_deep, tab_what, tab_chat = st.tabs(["📡 Overview", "🔍 Supplier deep dive", "🌪️ What-if scenario", "💬 Rail copilot"])

    with tab_over:
        c = st.columns(5)
        c[0].metric("Suppliers monitored", summary["suppliers"])
        c[1].metric("Act now (≥60)", summary["act"])
        c[2].metric("Watch (40–59)", summary["watch"])
        c[3].metric("Single-source suppliers", summary["single_source"])
        c[4].metric("€ at risk (6-week outage)", eur(summary["exposure_eur"]),
                    help="Contract penalty exposure if every act-now supplier fails for 6 weeks")

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
                              yaxis=dict(autorange="reversed"),
                              legend=dict(orientation="v", y=-0.08, yanchor="top", x=0, font_size=10),
                              xaxis=dict(range=[0, 100], tickvals=[0, 25, 50, 75, 100]))
            st.plotly_chart(fig, width="stretch")

        st.subheader("Watch list")
        rows = []
        for r in scores:
            s = m.suppliers()[r["id"]]
            rows.append({"ID": r["id"], "Supplier": s["name"], "Country": s["country"], "Makes": s["category"],
                         "Tier": s["tier"], "Risk": r["score"], "Band": r["band"],
                         "Agent events": len(agent.events_for(r["id"])), "Why": "; ".join(r["reasons"][:3])})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=330,
                     column_config={"Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%.0f"),
                                    "Why": st.column_config.TextColumn(width="large")})

        st.subheader("Agent risk scan")
        st.caption(f"{llm_name} searches live news per supplier region, industry and raw material, then extracts cited risk events.")
        default_ids = [r["id"] for r in scores[:8]]
        pick = st.multiselect("Suppliers to scan", options=list(m.suppliers()), default=default_ids,
                              format_func=lambda i: f"{i} · {m.suppliers()[i]['name']}")
        if st.button("▶ Run agent scan", type="primary", disabled=not (keys["llm"] and keys["tavily"]) or not pick):
            res, _ = run_streaming(wf.scan_many, pick, label=f"Scanning {len(pick)} suppliers")
            if res is not None:
                st.success("Scan complete. Scores updated.")
                time.sleep(0.6)
                st.rerun()

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
                                                  steps=[dict(range=[0, 40], color="#e8f1ea"), dict(range=[40, 60], color="#f7edd8"),
                                                         dict(range=[60, 100], color="#f6dfd9")])))
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

        if st.button("🛠 Generate mitigation plan", disabled=not keys["llm"]):
            with st.spinner(f"{llm_name} is drafting a mitigation plan..."):
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

    with tab_what:
        st.markdown("Describe any disruption, or let the agent pull **today's headlines** and propose threats to our supplier base. "
                    f"{llm_name} maps the event to suppliers, then the supply graph traces it to trains and euros.")

        with st.container(border=True):
            h1, h2 = st.columns([3, 1])
            h1.markdown("**📰 Today's threats from live news**")
            if h2.button("Scan headlines", width="stretch", disabled=not (keys["llm"] and keys["tavily"])):
                threats, _ = run_streaming(wf.headline_threats, label="Agent scanning world news")
                if threats is not None:
                    remember("threats", threats)
            threats = st.session_state.get("threats", [])
            if threats:
                tcols = st.columns(len(threats))
                for i, (col, th) in enumerate(zip(tcols, threats)):
                    with col:
                        st.markdown(f"**{th.get('headline', '')}**")
                        st.caption(th.get("why", ""))
                        if th.get("url"):
                            st.markdown(f"<a class='muted' href='{th['url']}' target='_blank'>source ↗</a>", unsafe_allow_html=True)
                        if st.button("Simulate →", key=f"th_{i}", width="stretch"):
                            st.session_state["scenario_text"] = th.get("scenario", th.get("headline", ""))
                            st.session_state["auto_run"] = True
            else:
                st.caption("Click **Scan headlines** to have the agent rank this week's news against our 32 suppliers.")

        cols = st.columns(len(EXAMPLES))
        for col, ex in zip(cols, EXAMPLES):
            if col.button(ex, width="stretch"):
                st.session_state["scenario_text"] = ex
                st.session_state["auto_run"] = True
        text = st.text_area("Scenario", key="scenario_text", height=80, placeholder="e.g. Port of Rotterdam closed by a cyber attack for 2 weeks")
        run_now = st.button("🌪️ Simulate impact", type="primary", disabled=not keys["llm"] or not text)
        if (run_now or st.session_state.pop("auto_run", False)) and text and keys["llm"]:
            res, _ = run_streaming(wf.scenario, text, label="Simulating disruption")
            if res is not None:
                remember("scenario", res)
                st.session_state.pop("response", None)
        sc = st.session_state.get("scenario")
        if sc:
            st.markdown(f"### ⚡ {sc.get('title', '')}")
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
            left, right = st.columns([3, 2])
            with left:
                if edges:
                    st.plotly_chart(sankey(edges, "Impact cascade: event → suppliers → components → trains", height=430), width="stretch")
            with right:
                if sc["projects"]:
                    st.plotly_chart(delivery_timeline(sc["projects"]), width="stretch")
                if sc.get("lat") is not None and sc["impacts"]:
                    hs = [m.suppliers()[i["supplier_id"]] for i in sc["impacts"]]
                    mf = go.Figure()
                    for h in hs:
                        mf.add_trace(go.Scattermap(lat=[sc["lat"], h["lat"]], lon=[sc["lon"], h["lon"]], mode="lines",
                                                   line=dict(width=2, color="rgba(194,65,45,0.5)"), hoverinfo="skip"))
                    mf.add_trace(go.Scattermap(lat=[sc["lat"]], lon=[sc["lon"]], mode="markers", marker=dict(size=40, color="rgba(194,65,45,0.3)"),
                                               text=[sc.get("title", "")], hoverinfo="text"))
                    mf.add_trace(go.Scattermap(lat=[h["lat"] for h in hs], lon=[h["lon"] for h in hs], mode="markers+text",
                                               marker=dict(size=12, color="#c2412d"), text=[h["name"] for h in hs], textposition="top right"))
                    mf.update_layout(map=dict(style="carto-positron", center=dict(lat=float(sc["lat"]), lon=float(sc["lon"])), zoom=2),
                                     height=230, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
                    st.plotly_chart(mf, width="stretch")
            hit = pd.DataFrame([{"Supplier": i["supplier"], "Why hit": i["reason"], "Capacity lost": f"{i['capacity_loss']:.0%}",
                                 "Exposure": eur(i["total_exposure_eur"])} for i in sc["impacts"]])
            if len(hit):
                st.dataframe(hit, hide_index=True, width="stretch")

            st.markdown("#### 🧭 Agent response plan")
            if st.button("Build response plan", type="primary", disabled=not keys["llm"]):
                trace, answer = [], ""
                with st.status("Agent building response plan", expanded=True) as status:
                    for step in agent.run(wf.response_prompt(sc), max_steps=8, tools=agent.RAIL_TOOLS):
                        if step["type"] == "answer":
                            answer = step["content"]
                        else:
                            trace.append(trace_line(step))
                            st.markdown(trace[-1], unsafe_allow_html=True)
                    status.update(label=f"Response plan ready ({len(trace)} agent steps)", state="complete", expanded=False)
                remember("response", {"trace": trace, "answer": answer})
            resp = st.session_state.get("response")
            if resp:
                with st.expander(f"Agent trace ({len(resp['trace'])} steps)"):
                    st.markdown("\n\n".join(resp["trace"]), unsafe_allow_html=True)
                st.markdown(resp["answer"])

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
                        st.markdown("\n\n".join(msg["trace"]), unsafe_allow_html=True)
                st.markdown(msg["content"])
        prompt = st.chat_input("Ask the rail copilot...", disabled=not keys["llm"], key="rail_chat_input") or preset
        if prompt:
            with st.chat_message("user"):
                st.markdown(prompt)
            history = [{"role": x["role"], "content": x["content"]} for x in st.session_state.chat[-6:]]
            st.session_state.chat.append({"role": "user", "content": prompt})
            with st.chat_message("assistant"):
                trace, answer = [], ""
                with st.status("Agent reasoning", expanded=True) as status:
                    for step in agent.run(prompt, history, tools=agent.RAIL_TOOLS):
                        if step["type"] == "answer":
                            answer = step["content"]
                        else:
                            trace.append(trace_line(step))
                            st.markdown(trace[-1], unsafe_allow_html=True)
                    status.update(label=f"Agent trace ({len(trace)} steps)", state="complete", expanded=False)
                st.markdown(answer)
            st.session_state.chat.append({"role": "assistant", "content": answer, "trace": trace})

