"""Streamlit helpers shared by all tabs: pills, agent streaming, demo cache, shortlist and risk lens state."""
import json
import queue
import threading

import streamlit as st

from core import agent, dataset as ds
from core.fmt import trace_line

BAND_COLOR = {"low": "#2f8a4e", "watch": "#c98a12", "act now": "#c2412d"}
ACCENT = "#1f5f8b"
MAX_SHORTLIST = 20


def pill(band: str, text: str | None = None) -> str:
    color = BAND_COLOR.get(band) or ds.LEVEL_COLOR.get(band, "#8a9a92")
    ink = "#1b2420" if color in (ds.LEVEL_COLOR["Medium"], BAND_COLOR["watch"]) else "white"  # white on yellow is unreadable
    return f'<span class="pill" style="background:{color};color:{ink}">{text or band.upper()}</span>'


def run_streaming(fn, *args, label="Agent working", keep=14, **kwargs):
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
                box.markdown("\n\n".join(lines[-keep:]), unsafe_allow_html=True)
            except queue.Empty:
                pass
        if "error" in out:
            status.update(label=f"Failed: {out['error']}", state="error")
            return None, lines
        status.update(label=f"{label}: done ({len(lines)} steps)", state="complete", expanded=False)
    return out.get("result"), lines


# Last successful results persist to cache/ so tabs open populated and the demo survives a slow API
def remember(key: str, value):
    st.session_state[key] = value
    try:
        (agent.CACHE / f"last_{key}.json").write_text(json.dumps(value, default=str))
    except OSError:
        pass


def restore(keys: list[str]):
    for k in keys:
        f = agent.CACHE / f"last_{k}.json"
        if k not in st.session_state and f.exists():
            st.session_state[k] = json.loads(f.read_text())


# ---------- shortlist ----------

def shortlist() -> list[str]:
    return st.session_state.setdefault("shortlist", [])


def add_to_shortlist(ids) -> tuple[list[str], list[str]]:
    """Add IDs, keeping order and the 20-supplier cap. Returns (added, skipped)."""
    sl = shortlist()
    added, skipped = [], []
    for sid in ids:
        if sid in sl:
            continue
        if len(sl) >= MAX_SHORTLIST:
            skipped.append(sid)
            continue
        sl.append(sid)
        added.append(sid)
    return added, skipped


def set_shortlist(ids):
    st.session_state["shortlist"] = list(dict.fromkeys(ids))[:MAX_SHORTLIST]


def notify_added(added, skipped):
    if added:
        st.toast(f"Added {len(added)} supplier(s) to the shortlist ({len(shortlist())}/{MAX_SHORTLIST})", icon="✅")
    if skipped:
        st.toast(f"Shortlist is full ({MAX_SHORTLIST}). Skipped {len(skipped)}.", icon="⚠️")


# ---------- risk lens ----------

def lens() -> tuple[str, dict]:
    name = st.session_state.get("lens_name", "Dataset TRI (official)")
    if name == "Custom":
        return name, st.session_state.get("custom_weights", ds.TRI_WEIGHTS)
    return name, ds.LENSES.get(name, ds.TRI_WEIGHTS)


def lens_label() -> str:
    name, _ = lens()
    return "TRI" if name.startswith("Dataset") else "Lens index"


def sid_label(sid: str) -> str:
    r = ds.df().loc[sid]
    return f"{sid} · {r['Supplier Name']} · TRI {r['Total_Risk_Index']}"
