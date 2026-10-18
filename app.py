"""RailRisk Radar: supplier selection and risk intelligence for Siemens rail procurement."""
import hmac
import os

import streamlit as st

# Streamlit Community Cloud passes keys via st.secrets; core/ reads os.environ. Real env vars win.
for _k in ("NEBIUS_API_KEY", "TAVILY_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER", "NEMOTRON_MODEL",
           "NEBIUS_BASE_URL", "CLAUDE_MODEL", "APP_USERS", "PERSIST_DEMO_CACHE"):
    try:
        if not os.getenv(_k) and _k in st.secrets:
            os.environ[_k] = str(st.secrets[_k])
    except Exception:  # no secrets.toml
        break

from core import dataset as ds, llm
from views import chat, compare, explore, profile, rail, research
from views.common import MAX_SHORTLIST, restore, set_shortlist, shortlist

st.set_page_config(page_title="RailRisk Radar", page_icon="🚆", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem;}
.pill {display:inline-block;padding:2px 10px;border-radius:99px;font-size:0.8rem;font-weight:600;color:white;vertical-align:middle}
.trace {font-family: ui-monospace, Menlo, monospace; font-size: 0.82rem; line-height:1.5}
.evt {border-left: 3px solid #c98a12; padding: 6px 12px; margin: 6px 0; background: rgba(127,127,127,0.06); border-radius: 0 6px 6px 0}
.muted {color: #6b7a73; font-size: 0.86rem}
div[data-testid="stMetricValue"] {font-size: 1.6rem}
</style>
""", unsafe_allow_html=True)


# ---------- jury login (APP_USERS="user:password,user2:password2"; unset = open) ----------

def users() -> dict:
    raw = os.getenv("APP_USERS", "")  # env, .env or st.secrets (bridged above)
    return dict(map(str.strip, u.split(":", 1)) for u in raw.split(",") if ":" in u)


def login_gate():
    accounts = users()
    if not accounts or st.session_state.get("user"):
        return
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("## 🚆 RailRisk Radar")
        st.caption("Supplier selection and risk intelligence for rail procurement")
        with st.form("login"):
            u = st.text_input("Username").strip()
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary", width="stretch"):
                if u in accounts and hmac.compare_digest(accounts[u].encode(), p.encode()):
                    st.session_state["user"] = u
                    st.rerun()
                st.error("Wrong username or password")
    st.stop()


login_gate()
restore(["research", "memo", "threats", "scenario", "response"])

# ---------- sidebar ----------

with st.sidebar:
    st.markdown("## 🚆 RailRisk Radar")
    st.caption("Supplier selection for rail procurement")
    keys = llm.keys_status()
    llm_name = "Claude" if keys["provider"] == "claude" else "Nemotron (Token Factory)"
    st.markdown(f"{llm_name}: {'🟢' if keys['llm'] else '🔴 no key'} · Web search: {'🟢' if keys['tavily'] else '🔴'}")
    models = llm.nemotron_models() if keys["llm"] and keys["provider"] == "nebius" else []
    if models:
        default = llm.default_model()
        # per session: the widget value lives in this user's session_state, set_model() scopes it to this run
        llm.set_model(st.selectbox("Model", models, index=models.index(default) if default in models else 0,
                                   key="llm_model"))
    else:
        llm.set_model(None)
        st.caption(f"Model: `{llm.model()}`")

    st.divider()
    st.markdown("**Risk lens**")
    lens_names = list(ds.LENSES) + ["Custom"]
    st.selectbox("Rank suppliers by", lens_names, key="lens_name", label_visibility="collapsed",
                 help="Re-weights the 18 risk scores for your sourcing situation. The official TRI stays visible everywhere.")
    if st.session_state.get("lens_name") == "Custom":
        with st.expander("Weights", expanded=True):
            base = st.session_state.get("custom_weights", ds.TRI_WEIGHTS)
            st.session_state["custom_weights"] = {
                c: st.slider(ds.label(c), 0, 30, int(round(base.get(c, 0) * 100)), key=f"w_{c}") / 100 for c in ds.SCORES}
    else:
        w = ds.normalize_weights(ds.LENSES[st.session_state.get("lens_name", lens_names[0])])
        st.caption("Top weights: " + ", ".join(f"{ds.label(k)} {v:.0%}" for k, v in sorted(w.items(), key=lambda t: -t[1])[:4]))

    st.divider()
    sl = shortlist()
    st.markdown(f"**Shortlist** ({len(sl)}/{MAX_SHORTLIST})")
    if sl:
        d = ds.df().loc[sl]
        st.dataframe(d[["Total_Risk_Index", "Total_Risk_Index_Level"]].rename(
            columns={"Total_Risk_Index": "TRI", "Total_Risk_Index_Level": "Level"}), width="stretch",
            height=min(36 * len(sl) + 38, 400))
        if st.button("Clear shortlist", width="stretch", key="sb_clear"):
            set_shortlist([])
            st.rerun()
    else:
        st.caption("Empty. Add suppliers from Find suppliers, the assistant, or a profile.")
    st.divider()
    st.caption(f"Dataset: {len(ds.df()):,} anonymized suppliers. TRI formula reproduced exactly "
               f"({ds.check_tri_formula():.0%} of rows).")

# ---------- tabs ----------

st.title("RailRisk Radar")
s = ds.summary()
st.caption(f"{s['suppliers']:,} suppliers · average TRI {s['avg_tri']} · {s['critical']} Critical · "
           f"{s['high']:,} High · {s['po_volume'] / 1e9:.1f} bn € purchase volume")

tabs = st.tabs(["🔎 Find suppliers", "⚖️ Compare shortlist", "🧬 Supplier profile", "💬 Ask the data",
                "🌐 Research agent", "🚆 Rail impact lab (demo data)"])
with tabs[0]:
    explore.render()
with tabs[1]:
    compare.render()
with tabs[2]:
    profile.render()
with tabs[3]:
    chat.render()
with tabs[4]:
    research.render()
with tabs[5]:
    rail.render(keys)
