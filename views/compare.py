"""Compare the shortlist (up to 20) side by side and justify the final choice."""
import pandas as pd
import streamlit as st

from core import dataset as ds
from views import charts, team
from views.common import MAX_SHORTLIST, lens, lens_label, set_shortlist, shortlist

JURY_EXAMPLE = ["SUPP_00012", "SUPP_00450", "SUPP_00731", "SUPP_00018"]


def ranking(ids: list[str], weights: dict) -> pd.DataFrame:
    d = ds.df().loc[ids].copy()
    d["Lens index"] = ds.lens_index(d, weights)
    d = d.sort_values(["Lens index", "Total_Risk_Index"])
    # which scores each supplier is best at within the set
    best = {sid: [] for sid in d.index}
    for c in ds.SCORES:
        mn = d[c].min()
        winners = d.index[d[c] == mn]
        if len(winners) == 1:
            best[winners[0]].append(ds.label(c))
    worst = d[ds.SCORES].idxmax(axis=1)
    return pd.DataFrame({
        "Rank": range(1, len(d) + 1), "ID": d.index, "Lens": d["Lens index"], "TRI": d["Total_Risk_Index"],
        "Level": d["Total_Risk_Index_Level"],
        "Critical scores": [sum(d.loc[i, ds.SCORES] >= 75) for i in d.index],
        "Worst": [f"{ds.label(c)} {d.at[i, c]}" for i, c in zip(d.index, worst)],
        "Safest in set at": [", ".join(best[i]) for i in d.index],
        "Delivery %": d["Supplier Delivery Rating"], "Confirm %": d["Order Confirmation Rate"],
        "Change %": d["Order Change Rate"], "PO €": d[ds.PO], "Sourcing": d["Sourcing Risk Level"],
        "Complexity": d["Supply Chain Complexity"],
    })


def render():
    ids = shortlist()
    st.session_state["shortlist_ms"] = list(ids)  # widget mirrors the shortlist, edits flow back via on_change
    top = st.columns([5, 1, 1])
    top[0].multiselect(f"Shortlist (up to {MAX_SHORTLIST})", ds.df().index.tolist(), max_selections=MAX_SHORTLIST,
                       key="shortlist_ms", placeholder="Add suppliers by ID",
                       on_change=lambda: set_shortlist(st.session_state["shortlist_ms"]))
    if top[1].button("Jury example", width="stretch", help=", ".join(JURY_EXAMPLE)):
        set_shortlist(JURY_EXAMPLE)
        st.rerun()
    if top[2].button("Clear", width="stretch", disabled=not ids):
        set_shortlist([])
        st.rerun()
    if len(ids) < 2:
        st.info("Add at least two suppliers: tick rows in **Find suppliers**, ask the assistant to shortlist them, "
                "or load the jury example above.")
        return

    lens_name, weights = lens()
    rk = ranking(ids, weights)
    order = rk["ID"].tolist()
    show = rk.drop(columns=["Lens"]) if lens_label() == "TRI" else rk
    lead = rk.iloc[0]
    if lens_label() == "TRI":
        st.markdown(f"**{lead['ID']}** has the lowest TRI ({lead['TRI']}, {lead['Critical scores']} critical score(s)). "
                    f"Runner-up **{rk.iloc[1]['ID']}** at {rk.iloc[1]['TRI']}.")
    else:
        st.markdown(f"**{lead['ID']}** ranks first under **{lens_name}** with lens index {lead['Lens']:.1f} "
                    f"(TRI {lead['TRI']}, {lead['Critical scores']} critical score(s)). "
                    f"Runner-up **{rk.iloc[1]['ID']}** at {rk.iloc[1]['Lens']:.1f}.")
    st.dataframe(show, hide_index=True, width="stretch",
                 column_config={"Lens": st.column_config.NumberColumn(lens_label(), format="%.1f"),
                                "TRI": st.column_config.ProgressColumn("TRI", min_value=0, max_value=100, format="%d"),
                                "PO €": st.column_config.NumberColumn(format="€%,.0f"),
                                "Delivery %": st.column_config.NumberColumn(format="%.1f"),
                                "Confirm %": st.column_config.NumberColumn(format="%.1f"),
                                "Change %": st.column_config.NumberColumn(format="%.1f"),
                                "Safest in set at": st.column_config.TextColumn(width="medium")})

    st.markdown("##### Risk heatmap: rows ranked by the current lens, columns grouped by risk family")
    st.plotly_chart(charts.heatmap(ids, order), width="stretch")
    a, b = st.columns(2)
    with a:
        st.plotly_chart(charts.stacked_tri(ids, order), width="stretch")
    with b:
        pick = st.multiselect("Overlay risk profiles (up to 5)", order, default=order[:3], max_selections=5, key="radar_ids")
        if pick:
            st.plotly_chart(charts.radar(pick), width="stretch")

    st.markdown("#### Head to head")
    h = st.columns(2)
    x = h[0].selectbox("Supplier A", order, index=0, key="h2h_a")
    y = h[1].selectbox("Supplier B", order, index=1, key="h2h_b")
    if x != y:
        st.plotly_chart(charts.head_to_head(x, y), width="stretch")

    team.render(order, weights, lens_name)
