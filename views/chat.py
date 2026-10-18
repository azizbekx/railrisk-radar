"""Ask the data: tool-calling assistant grounded in the 10,000-supplier dataset, with charts it chooses itself."""
import streamlit as st

from core import agent, llm
from core.fmt import trace_line
from views import charts
from views.common import add_to_shortlist, notify_added, shortlist

PRESETS = {  # short button label -> full question
    "Lowest financial risk of 3?": "Which of SUPP_00012, SUPP_00450 and SUPP_00731 has the lowest financial risk?",
    "Why is SUPP_00018 so risky?": "Why is the Total Risk Index of SUPP_00018 so high?",
    "Shortlist 5 reliable, easy swaps": "Find 5 easy-to-replace suppliers with delivery rating above 97% and no Critical "
                                        "scores, and shortlist them",
    "Shortlist: compliance & cyber": "How does my shortlist compare on compliance and cyber risk?",
}


def show(msg: dict, idx: int):
    if msg.get("trace"):
        with st.expander(f"Agent trace ({len(msg['trace'])} steps)"):
            st.markdown("\n\n".join(msg["trace"]), unsafe_allow_html=True)
    st.markdown(msg["content"])
    for j, spec in enumerate(msg.get("charts", [])):
        try:
            fig = charts.from_spec(spec)
        except Exception as e:
            st.caption(f"chart failed: {e}")
            continue
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key=f"chat_fig_{idx}_{j}")


def render():
    st.markdown("Ask in plain language. The assistant queries the dataset through tools, so every number is traceable "
                "in the agent trace, and it draws charts when they help.")
    chat = st.session_state.setdefault("data_chat", [])
    qc = st.columns(len(PRESETS))
    preset = None
    for col, (short, q) in zip(qc, PRESETS.items()):
        if col.button(short, width="stretch", key=f"preset_{q[:20]}", help=q):
            preset = q
    for i, msg in enumerate(chat):
        with st.chat_message(msg["role"]):
            show(msg, i)
    live = st.container()
    if chat and st.button("Clear conversation", key="clear_chat"):
        st.session_state["data_chat"] = []
        st.rerun()
    prompt = st.chat_input("e.g. Which High-sourcing-risk suppliers have the best delivery rating?",
                           disabled=not llm.keys_status()["llm"]) or preset
    if not prompt:
        return
    with live:
        turn(chat, prompt)


def turn(chat: list, prompt: str):
    with st.chat_message("user"):
        st.markdown(prompt)
    history = [{"role": m["role"], "content": m["content"]} for m in chat[-8:]]
    ctx = f"\n\n(Buyer's current shortlist: {', '.join(shortlist()) or 'empty'})"
    chat.append({"role": "user", "content": prompt})
    with st.chat_message("assistant"):
        trace, answer, specs, added = [], "", [], []
        with st.status("Querying the supplier data", expanded=True) as status:
            for step in agent.run(prompt + ctx, history, tools=agent.DATA_TOOLS, system=agent.DATA_SYSTEM):
                if step["type"] == "answer":
                    answer = step["content"]
                    continue
                if step["type"] == "tool_result" and isinstance(step["content"], dict):
                    if step["name"] == "show_chart":
                        specs.append(step["content"])
                    elif step["name"] == "add_to_shortlist":
                        added += step["content"].get("added", [])
                trace.append(trace_line(step))
                st.markdown(trace[-1], unsafe_allow_html=True)
            status.update(label=f"Agent trace ({len(trace)} steps)", state="complete", expanded=False)
        msg = {"role": "assistant", "content": answer, "trace": trace, "charts": specs[:2]}
        show({**msg, "trace": []}, len(chat))
    chat.append(msg)
    if added:
        notify_added(*add_to_shortlist(added))
        st.rerun()  # refresh sidebar and Compare, which rendered before this turn
