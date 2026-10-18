"""Find suppliers: filter and rank the 10,000 suppliers, then shortlist up to 20."""
import numpy as np
import pandas as pd
import streamlit as st

from core import dataset as ds
from core.fmt import eur
from views import charts
from views.common import MAX_SHORTLIST, add_to_shortlist, lens, lens_label, notify_added, shortlist

PO_STEPS = [10_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 2_500_000, 5_000_000, 10_000_000, 25_000_000, 50_000_000]


def filters() -> pd.DataFrame:
    d = ds.df()
    with st.container(border=True):
        c = st.columns([2, 2, 2, 2])
        text = c[0].text_input("Supplier ID or name", placeholder="SUPP_00012 or 'Apex'", key="f_text")
        tri = c[1].slider("Total Risk Index", 0, 100, (0, 100), key="f_tri")
        levels = c[2].multiselect("TRI level", ds.LEVELS, key="f_levels", placeholder="any")
        sourcing = c[3].multiselect("Sourcing risk (replaceability)", ds.CAT_ORDER["Sourcing Risk Level"], key="f_src",
                                    placeholder="any")
        c = st.columns([2, 2, 2, 2])
        complexity = c[0].multiselect("Supply chain complexity", ds.CAT_ORDER["Supply Chain Complexity"], key="f_cx",
                                      placeholder="any")
        delivery = c[1].slider("Min. delivery rating %", 60, 100, 60, key="f_del")
        confirm = c[2].slider("Min. order confirmation %", 60, 100, 60, key="f_conf")
        po = c[3].select_slider("PO volume (EUR)", PO_STEPS, (PO_STEPS[0], PO_STEPS[-1]), format_func=eur, key="f_po")
        c = st.columns([4, 2, 2])
        knockout = c[0].multiselect("Knock-out: exclude suppliers that are **Critical** in", ds.SCORES,
                                    format_func=ds.label, key="f_ko", placeholder="e.g. Financial Health, Compliance Risk")
        max_change = c[1].slider("Max. order change rate %", 0, 35, 35, key="f_chg")
        max_score = c[2].slider("No single score above", 50, 100, 100, key="f_max",
                                help="Drop suppliers whose worst individual score exceeds this value")

    m = d["Total_Risk_Index"].between(*tri) & (d["Supplier Delivery Rating"] >= delivery) & \
        (d["Order Confirmation Rate"] >= confirm) & d[ds.PO].between(*po) & (d["Order Change Rate"] <= max_change)
    if text:
        sid = ds.resolve(text)
        m &= (d.index == sid) if sid else d["Supplier Name"].str.contains(text, case=False, regex=False) | \
            d.index.str.contains(text, case=False, regex=False)
    if levels:
        m &= d["Total_Risk_Index_Level"].isin(levels)
    if sourcing:
        m &= d["Sourcing Risk Level"].isin(sourcing)
    if complexity:
        m &= d["Supply Chain Complexity"].isin(complexity)
    for col in knockout:
        m &= d[col] < 75
    if max_score < 100:
        m &= d[ds.SCORES].max(axis=1) <= max_score
    return d[m]


def render():
    st.markdown("Narrow 10,000 suppliers down to a shortlist. Rank by the official **Total Risk Index** or by a "
                "**risk lens** (sidebar) that re-weights the 18 scores for your sourcing situation.")
    d = filters()
    lens_name, weights = lens()
    d = d.assign(**{"Lens index": ds.lens_index(d, weights)}) if len(d) else d.assign(**{"Lens index": []})
    rank_col = "Total_Risk_Index" if lens_label() == "TRI" else "Lens index"

    s = ds.summary(d)
    k = st.columns(5)
    k[0].metric("Matching suppliers", f"{s['suppliers']:,} / {len(ds.df()):,}")
    k[1].metric("Average TRI", s["avg_tri"])
    k[2].metric("Critical TRI", s["critical"])
    k[3].metric("PO volume", eur(s["po_volume"]))
    k[4].metric("Shortlist", f"{len(shortlist())}/{MAX_SHORTLIST}")
    if not len(d):
        st.warning("No supplier passes these filters. Loosen one of them.")
        return

    left, right = st.columns([3, 2])
    with left:
        sort = st.radio("Rank by", [rank_col, "Supplier Delivery Rating", "Order Confirmation Rate", ds.PO],
                        horizontal=True, format_func=lambda c: {"Total_Risk_Index": "TRI (lowest first)",
                                                                  "Lens index": f"{lens_name} (lowest first)",
                                                                  "Supplier Delivery Rating": "Delivery rating",
                                                                  "Order Confirmation Rate": "Confirmation rate",
                                                                  ds.PO: "PO volume"}.get(c, ds.label(c)),
                        key="f_sort")
        d = d.sort_values(sort, ascending=sort in ("Total_Risk_Index", "Lens index"))
        worst = d[ds.SCORES].idxmax(axis=1)
        view = pd.DataFrame({
            "ID": d.index, "Supplier": d["Supplier Name"],
            **({"Lens": d["Lens index"]} if rank_col == "Lens index" else {}),
            "TRI": d["Total_Risk_Index"], "Level": d["Total_Risk_Index_Level"],
            "Worst score": [f"{ds.label(c)} {d.at[i, c]}" for i, c in zip(d.index, worst)],
            "Delivery %": d["Supplier Delivery Rating"], "Confirm %": d["Order Confirmation Rate"],
            "Change %": d["Order Change Rate"], "PO €": d[ds.PO], "Sourcing": d["Sourcing Risk Level"],
            "Complexity": d["Supply Chain Complexity"], "★": np.where(d.index.isin(shortlist()), "★", ""),
        })
        sel = st.dataframe(
            view.head(1000), hide_index=True, width="stretch", height=430, on_select="rerun",
            selection_mode="multi-row", key="explore_table",
            column_config={"TRI": st.column_config.ProgressColumn("TRI", min_value=0, max_value=100, format="%d"),
                           "Lens": st.column_config.NumberColumn("Lens", format="%.1f"),
                           "Worst score": st.column_config.TextColumn(width="medium"),
                           "Delivery %": st.column_config.NumberColumn(format="%.1f"),
                           "Confirm %": st.column_config.NumberColumn(format="%.1f"),
                           "Change %": st.column_config.NumberColumn(format="%.1f"),
                           "PO €": st.column_config.NumberColumn(format="€%,.0f"),
                           "★": st.column_config.TextColumn("★", width="small", help="on shortlist")})
        picked = [view.iloc[i]["ID"] for i in sel.selection.rows] if sel and sel.selection else []
        b = st.columns([2, 2, 3])
        if b[0].button(f"➕ Add selected ({len(picked)})", disabled=not picked, type="primary", width="stretch",
                       help="Add the ticked rows to the shortlist"):
            notify_added(*add_to_shortlist(picked))
            st.rerun()
        if b[1].button("➕ Add top 5", width="stretch", help="Add the top 5 of this ranking to the shortlist"):
            notify_added(*add_to_shortlist(list(d.index[:5])))
            st.rerun()
        b[2].caption(f"Showing {min(len(view), 1000):,} of {len(view):,}. Tick rows to select. "
                     "Then open **Compare** to see them side by side.")
    with right:
        st.plotly_chart(charts.landscape(d, shortlist(), rank_col), width="stretch")
        src = pd.crosstab(d["Sourcing Risk Level"], d["Total_Risk_Index_Level"]).reindex(
            index=ds.CAT_ORDER["Sourcing Risk Level"], columns=ds.LEVELS, fill_value=0)
        st.caption("TRI level by sourcing risk: hard-to-replace suppliers skew riskier "
                   f"(avg TRI {d.loc[d['Sourcing Risk Level'] == 'High', 'Total_Risk_Index'].mean():.0f} vs "
                   f"{d.loc[d['Sourcing Risk Level'] == 'Low', 'Total_Risk_Index'].mean():.0f} for easy-to-replace).")
        st.dataframe(src, width="stretch")
