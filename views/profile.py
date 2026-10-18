"""One supplier in depth: exact TRI explanation, percentiles, operations and lower-risk swap candidates."""
import plotly.graph_objects as go
import streamlit as st

from core import dataset as ds
from core.fmt import eur
from views import charts
from views.common import add_to_shortlist, notify_added, pill, shortlist, sid_label


def render():
    ids = ds.df().index.tolist()
    default = st.session_state.get("profile_id") or (shortlist()[0] if shortlist() else "SUPP_00018")
    sid = st.selectbox("Supplier", ids, index=ids.index(default), format_func=sid_label, key="profile_sel")
    st.session_state["profile_id"] = sid
    r = ds.df().loc[sid]
    e = ds.explain(sid)

    head, gauge = st.columns([3, 1])
    with head:
        badge = pill(e["level"], f"TRI {e['total_risk_index']} · {e['level'].upper()}")
        st.markdown(f"### {sid} · {r['Supplier Name']} {badge}", unsafe_allow_html=True)
        st.markdown(ds.narrative(sid))
        st.caption(f"Sourcing risk **{r['Sourcing Risk Level']}** · supply chain **{r['Supply Chain Complexity']}** · "
                   f"PO volume **{eur(r[ds.PO])}** · TRI recomputed from the 18 weighted scores: {e['recomputed']:.2f} → "
                   f"{round(e['recomputed'])}")
        b = st.columns([1, 3])
        on = sid in shortlist()
        if b[0].button("★ On shortlist" if on else "➕ Shortlist", disabled=on, width="stretch"):
            notify_added(*add_to_shortlist([sid]))
            st.rerun()
    with gauge:
        g = go.Figure(go.Indicator(
            mode="gauge+number", value=e["total_risk_index"], number=dict(suffix="/100", font=dict(color="#1b2420")),
            gauge=dict(axis=dict(range=[0, 100], tickvals=[0, 25, 50, 75, 100]), bar=dict(color="#1b2420", thickness=0.25),
                       steps=[dict(range=[a, b], color=ds.LEVEL_COLOR[l]) for (a, b), l in
                              zip([(0, 25), (25, 50), (50, 75), (75, 100)], ds.LEVELS)])))
        g.update_layout(height=180, margin=dict(l=30, r=30, t=10, b=0))
        st.plotly_chart(g, width="stretch")
        st.caption(f"Riskier than {e['riskier_than_pct']:.0f}% of suppliers")

    a, b = st.columns([3, 2])
    with a:
        st.plotly_chart(charts.breakdown(sid), width="stretch")
    with b:
        st.plotly_chart(charts.score_bars(sid), width="stretch")

    st.markdown("#### Operational performance (not part of the TRI)")
    k = st.columns(4)
    for col, o in zip(k, e["operational_metrics"]):
        v, avg = o["value"], o["average"]
        if o["metric"] == ds.PO:
            col.metric("PO volume (exposure)", eur(v), f"larger than {o['riskier_than_pct']:.0f}% of suppliers", delta_color="off")
        else:
            unit = "%"
            col.metric(o["metric"], f"{v:.1f}{unit}", f"{v - avg:+.1f} vs avg {avg:.1f}",
                       delta_color="normal" if o["metric"] in ds.HIGHER_IS_BETTER else "inverse")
    st.caption("Delivery rating correlates strongly with the TRI (r = −0.71) even though it is not part of the formula: "
               "a cross-check that the risk scores predict real delivery problems.")

    st.markdown("#### Lower-risk alternatives with a similar profile")
    alt = ds.similar_lower_risk(sid, 6)
    if not len(alt):
        st.success("No supplier with the same sourcing risk and complexity is at least 10 points safer.")
        return
    st.caption(f"Same sourcing risk ({r['Sourcing Risk Level']}) and complexity ({r['Supply Chain Complexity']}), "
               "closest PO volume, TRI at least 10 points lower.")
    view = alt[["Supplier Name", "Total_Risk_Index", "Total_Risk_Index_Level", "Supplier Delivery Rating",
                "Order Confirmation Rate", ds.PO]].rename(columns={"Total_Risk_Index": "TRI", "Total_Risk_Index_Level": "Level",
                                                                   "Supplier Delivery Rating": "Delivery %",
                                                                   "Order Confirmation Rate": "Confirm %", ds.PO: "PO €"}).rename_axis("ID")
    st.dataframe(view, width="stretch", column_config={
        "TRI": st.column_config.ProgressColumn("TRI", min_value=0, max_value=100, format="%d"),
        "PO €": st.column_config.NumberColumn(format="€%,.0f")})
    if st.button(f"➕ Shortlist {sid} with these {len(alt)} alternatives"):
        notify_added(*add_to_shortlist([sid] + list(alt.index)))
        st.rerun()
