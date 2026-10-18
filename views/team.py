"""Ask the agent team (in Compare): a leader agent briefs four specialist agents that analyse the shortlist in
parallel, then decides and writes the selection memo. Each specialist designs its own chart, drawn from the data."""
import queue
import re
import threading
import time

import streamlit as st

from core import dataset as ds, llm, team
from views import charts
from views.common import remember

ICON = {"status": "⏳", "done": "✅", "error": "⚠️", "thought": "💭"}


def render(order: list[str], weights: dict, lens_name: str):
    st.markdown("#### 🤝 Ask the agent team")
    st.caption("A leader agent decides how much each risk area matters for this purchase and briefs four specialist "
               "agents. They analyse the shortlist at the same time and each designs a chart from the data. The leader "
               "then weighs their reports, picks the supplier and writes the selection memo. Every number comes from the dataset.")
    c = st.columns([5, 2])
    context = c[0].text_input("Buying context", key="team_ctx",
                              placeholder="e.g. brake control units for a regional train, safety-critical, 5-year frame contract")
    c[1].markdown("&nbsp;")
    if c[1].button("Ask the agent team", type="primary", width="stretch", disabled=not llm.keys_status()["llm"]):
        res = run_live(order, context, lens_name, weights)
        if res:
            remember("team", res)
    res = st.session_state.get("team")
    if res and set(res["ids"]) == set(order):
        show(res)
    elif res:
        st.caption("The shortlist changed since the team last ran. Ask again.")


def run_live(ids: list[str], context: str, lens_name: str, weights: dict) -> dict | None:
    """Run the team in a thread; the leader and the four specialists each stream into their own box."""
    q, out = queue.Queue(), {}

    def target():
        try:
            out["result"] = team.run(ids, context, lens_name, weights, log=q.put)
        except Exception as e:
            out["error"] = e

    th = threading.Thread(target=target, daemon=True)
    th.start()
    live = st.empty()
    with live.container():
        leader_box = st.empty()
        boxes = dict(zip(team.AGENTS, (col.empty() for col in st.columns(len(team.AGENTS)))))
    lines = {a: [] for a in ["Leader", *team.AGENTS]}
    started, finished, t0, drawn = {}, {}, time.time(), 0.0
    while th.is_alive() or not q.empty():
        try:
            ev = q.get(timeout=0.3)
            a = ev.get("agent", "Leader")
            lines[a].append(f"{ICON.get(ev['type'], '')} {ev['content']}")
            started.setdefault(a, time.time())
            if ev["type"] in ("done", "error"):
                finished.setdefault(a, time.time())
        except queue.Empty:
            if time.time() - drawn < 1:  # nothing new: only tick the timers once a second
                continue
        drawn = time.time()
        with leader_box.container(border=True):
            st.markdown(f"**🧭 Leader agent** <span class='muted'>· {time.time() - t0:.0f}s</span>", unsafe_allow_html=True)
            st.markdown("\n\n".join(lines["Leader"][-3:]))
        for a, box in boxes.items():
            state = (f"done in {finished[a] - started[a]:.1f}s" if a in finished else
                     f"working… {time.time() - started[a]:.0f}s" if a in started else "waiting for the brief")
            with box.container(border=True):
                st.markdown(f"**{team.AGENTS[a]['icon']} {a}**  \n<span class='muted'>{state}</span>", unsafe_allow_html=True)
                st.markdown("\n\n".join(lines[a][-2:]) or "…")
    live.empty()
    if "error" in out:
        st.error(f"The agent team failed: {out['error']}")
        return None
    return out["result"]


def show(res: dict):
    left, right = st.columns([2, 3])
    with left:
        st.graphviz_chart(team.flow_dot(res), width="stretch")
        st.caption(f"**Leader's weighting:** {res.get('why') or 'taken from the risk lens'}  \n"
                   f"Lens: {res['lens']} · {res.get('model', '')} · {res['created_at']}")
        if res.get("leader_reasoning"):
            with st.expander("🧠 How the leader reasoned"):
                st.code(res["leader_reasoning"], language=None, wrap_lines=True, height=300)
    with right:
        with st.container(border=True, height=520):
            # demote the memo's headings two levels so its H1 doesn't dwarf the page
            st.markdown(re.sub(r"^(#{1,4}) ", lambda m: "#" * (len(m.group(1)) + 2) + " ", res["memo"], flags=re.M))
        st.download_button("⬇ Download memo (.md)", res["memo"], file_name=f"selection_memo_{res['pick']}.md",
                           mime="text/markdown")
    a, b = st.columns(2)
    with a:
        st.markdown("##### Team scorecard: risk per area, weight under each agent")
        st.plotly_chart(charts.team_scorecard(res), width="stretch", key="team_scorecard")
    with b:
        st.markdown("##### How each team score adds up")
        st.plotly_chart(charts.team_contributions(res), width="stretch", key="team_contrib")
    st.markdown("##### The specialists' reports")
    names = list(res["reports"])
    for i in range(0, len(names), 2):
        for col, name in zip(st.columns(2), names[i:i + 2]):
            with col, st.container(border=True):
                agent_card(name, res["reports"][name], res)


def agent_card(name: str, rep: dict, res: dict):
    st.markdown(f"**{team.AGENTS[name]['icon']} {name} agent** · weight {res['weights'][name]:.0%} · picks "
                f"**{rep.get('best', '?')}** <span class='muted'>· {rep.get('confidence', '?')} confidence · "
                f"{rep.get('seconds', '?')}s</span>", unsafe_allow_html=True)
    if rep.get("brief"):
        st.caption(f"Leader's brief: {rep['brief']}")
    st.markdown(rep.get("verdict", ""))
    findings = [f"- {f}" for f in rep.get("findings") or [] if isinstance(f, str)]
    flags = [f"- 🚩 **{f.get('supplier', '')}**: {f.get('issue', '')}" for f in rep.get("red_flags") or [] if isinstance(f, dict)]
    if findings or flags:
        st.markdown("\n".join(findings + flags))
    allowed = team.chart_columns(name)
    spec, fig = rep.get("chart"), charts.custom(rep.get("chart"), res["ids"], allowed)
    designed = fig is not None
    if not designed:
        spec = team.AGENTS[name]["chart"]
        fig = charts.custom(spec, res["ids"], allowed)
    if fig is not None:
        st.plotly_chart(fig, width="stretch", key=f"team_fig_{name}")
        st.caption(("Chart designed by the agent" if designed else "Default chart (the agent's design could not be drawn)")
                   + f": {str(spec.get('kind')).replace('_', ' ')} of " + ", ".join(ds.label(str(c)) for c in spec.get("columns") or []))
    if rep.get("reasoning"):
        with st.expander("🧠 How the agent reasoned"):
            st.code(rep["reasoning"], language=None, wrap_lines=True, height=300)
