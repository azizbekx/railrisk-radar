"""The Siemens supplier risk dataset (10,000 anonymized suppliers): loading, exact TRI explanation,
filtering, comparison and buyer-defined risk lenses."""
import difflib
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "supplier_risk_dataset.csv"

# Total_Risk_Index = round(sum(score * weight)), Python/banker's rounding. Recovered by regression and
# verified exact on all 10,000 rows (see check_tri_formula).
TRI_WEIGHTS = {
    "Operational_Resilience_Score": 0.10,
    "Financial_Health_Score": 0.10,
    "Quality_Risk_Score": 0.10,
    "Compliance_Risk_Score": 0.08,
    "Credit_Rating_Score": 0.06,
    "Safety_Incident_Score": 0.06,
    "Sub_Tier_Visibility_Score": 0.06,
    "Geopolitical_Risk_Score": 0.05,
    "Governance_Risk_Score": 0.05,
    "ESG_Performance_Score": 0.05,
    "Environmental_Exposure_Score": 0.04,
    "Labor_Stability_Score": 0.04,
    "Digital_Security_Score": 0.04,
    "Political_Stability_Score": 0.04,
    "Industry_Benchmark_Score": 0.04,
    "Market_Sentiment_Score": 0.03,
    "Media_Sentiment_Score": 0.03,
    "External_Intelligence_Score": 0.03,
}
SCORES = list(TRI_WEIGHTS)

# Score families, used to group charts and research findings
GROUPS = {
    "Financial": ["Financial_Health_Score", "Credit_Rating_Score"],
    "Operations & quality": ["Operational_Resilience_Score", "Quality_Risk_Score", "Sub_Tier_Visibility_Score",
                             "Digital_Security_Score", "Industry_Benchmark_Score"],
    "Legal & governance": ["Compliance_Risk_Score", "Governance_Risk_Score"],
    "People & ESG": ["Safety_Incident_Score", "Labor_Stability_Score", "ESG_Performance_Score"],
    "Location & politics": ["Geopolitical_Risk_Score", "Political_Stability_Score", "Environmental_Exposure_Score"],
    "Reputation & intelligence": ["Media_Sentiment_Score", "Market_Sentiment_Score", "External_Intelligence_Score"],
}

PO = "Purchase Order Volume (EUR)"
OPS = ["Supplier Delivery Rating", "Order Confirmation Rate", "Order Change Rate", PO]
HIGHER_IS_BETTER = {"Supplier Delivery Rating", "Order Confirmation Rate"}
CATEGORICAL = ["Sourcing Risk Level", "Supply Chain Complexity"]
CAT_ORDER = {"Sourcing Risk Level": ["Low", "Medium", "High"], "Supply Chain Complexity": ["Simple", "Moderate", "Complex"]}

LEVELS = ["Low", "Medium", "High", "Critical"]
LEVEL_COLOR = {"Low": "#2f8a4e", "Medium": "#c9a227", "High": "#e0794f", "Critical": "#c2412d"}

# Buyer risk lenses: re-weight the same 18 scores for a sourcing situation. "Dataset TRI" is the official index.
LENSES = {
    "Dataset TRI (official)": TRI_WEIGHTS,
    "Safety-critical component": {**{s: 0.02 for s in SCORES}, "Quality_Risk_Score": 0.20, "Safety_Incident_Score": 0.14,
                                  "Operational_Resilience_Score": 0.14, "Compliance_Risk_Score": 0.10,
                                  "Sub_Tier_Visibility_Score": 0.10},
    "Long-term strategic partner": {**{s: 0.02 for s in SCORES}, "Financial_Health_Score": 0.18, "Credit_Rating_Score": 0.14,
                                    "Governance_Risk_Score": 0.12, "Operational_Resilience_Score": 0.10,
                                    "Geopolitical_Risk_Score": 0.08, "Political_Stability_Score": 0.06},
    "ESG & compliance first": {**{s: 0.02 for s in SCORES}, "ESG_Performance_Score": 0.18, "Compliance_Risk_Score": 0.16,
                               "Labor_Stability_Score": 0.10, "Governance_Risk_Score": 0.10, "Safety_Incident_Score": 0.10,
                               "Environmental_Exposure_Score": 0.08},
}


def check_tri_formula() -> float:
    """Share of rows where the recovered weights reproduce Total_Risk_Index exactly."""
    d = df()
    raw = sum(d[c] * round(w * 100) for c, w in TRI_WEIGHTS.items()) / 100
    return float((raw.round() == d["Total_Risk_Index"]).mean())


def label(col: str) -> str:
    return col.replace("_Score", "").replace("_", " ")


def level(v: float) -> str:
    return "Critical" if v >= 75 else "High" if v >= 50 else "Medium" if v >= 25 else "Low"


@lru_cache
def df() -> pd.DataFrame:
    d = pd.read_csv(CSV).set_index("supplierID", drop=False)
    # share of suppliers with a strictly lower index, i.e. "riskier than X%"
    d["TRI_Percentile"] = ((d["Total_Risk_Index"].rank(method="min") - 1) / len(d) * 100).round(1)
    return d


@lru_cache
def means() -> pd.Series:
    return df()[SCORES + ["Total_Risk_Index"] + OPS].mean()


def normalize_weights(w: dict) -> dict:
    total = sum(max(v, 0) for v in w.values()) or 1
    return {k: max(v, 0) / total for k, v in w.items() if k in TRI_WEIGHTS}


def lens_index(d: pd.DataFrame, weights: dict) -> pd.Series:
    w = normalize_weights(weights)
    return sum(d[c] * v for c, v in w.items()).round(1)


def riskier_than(col: str, value: float) -> float:
    """Share of suppliers (in %) that this value is riskier than."""
    s = df()[col]
    worse = s > value if col in HIGHER_IS_BETTER else s < value
    return round(float(worse.mean() * 100), 1)


# ---------- lookup ----------

ID_RE = re.compile(r"SUPP[_\s-]?(\d{1,5})", re.I)


def resolve(ref) -> str | None:
    """Supplier ID from an ID ('SUPP_00018', '18', 'supp 18') or a supplier name (fuzzy)."""
    if ref is None:
        return None
    ref = str(ref).strip()
    d = df()
    m = ID_RE.search(ref) or (re.fullmatch(r"\d{1,5}", ref) and re.match(r"(\d+)", ref))
    if m:
        sid = f"SUPP_{int(m.group(1)):05d}"
        return sid if sid in d.index else None
    names = d["Supplier Name"].str.lower()
    hit = d.index[names == ref.lower()]
    if len(hit):
        return hit[0]
    close = difflib.get_close_matches(ref.lower(), names.tolist(), n=1, cutoff=0.85)
    return d.index[names == close[0]][0] if close else None


def resolve_many(refs) -> tuple[list[str], list[str]]:
    if isinstance(refs, str):
        refs = re.split(r"[,;\s]+(?=SUPP|supp|\d)", refs) if ID_RE.search(refs) else [refs]
    ok, bad = [], []
    for r in refs:
        sid = resolve(r)
        (ok if sid else bad).append(sid or str(r))
    return list(dict.fromkeys(ok)), bad


def resolve_column(name: str) -> str | None:
    """Map loose wording ('financial risk', 'delivery', 'tri') onto a dataset column."""
    if not name:
        return None
    cols = list(df().columns)
    if name in cols:
        return name
    key = re.sub(r"[^a-z]", "", name.lower().replace("score", "").replace("risk", ""))
    aliases = {"tri": "Total_Risk_Index", "total": "Total_Risk_Index", "totalindex": "Total_Risk_Index",
               "overall": "Total_Risk_Index", "financial": "Financial_Health_Score", "finance": "Financial_Health_Score",
               "credit": "Credit_Rating_Score", "delivery": "Supplier Delivery Rating", "otd": "Supplier Delivery Rating",
               "confirmation": "Order Confirmation Rate", "orderchange": "Order Change Rate", "changes": "Order Change Rate",
               "po": PO, "povolume": PO, "spend": PO, "volume": PO, "purchaseorder": PO, "esg": "ESG_Performance_Score",
               "sourcing": "Sourcing Risk Level", "complexity": "Supply Chain Complexity", "quality": "Quality_Risk_Score",
               "cyber": "Digital_Security_Score", "safety": "Safety_Incident_Score", "labor": "Labor_Stability_Score",
               "labour": "Labor_Stability_Score", "environment": "Environmental_Exposure_Score",
               "media": "Media_Sentiment_Score", "name": "Supplier Name"}
    if key in aliases:
        return aliases[key]
    norm = {re.sub(r"[^a-z]", "", c.lower().replace("score", "").replace("risk", "")): c for c in cols}
    if key in norm:
        return norm[key]
    close = difflib.get_close_matches(key, list(norm), n=1, cutoff=0.6)
    if close:
        return norm[close[0]]
    for k, c in norm.items():
        if key and key in k:
            return c
    return None


# ---------- explanation ----------

def explain(sid: str) -> dict:
    """Exact decomposition of a supplier's Total_Risk_Index into weighted score contributions."""
    r = df().loc[sid]
    mu = means()
    parts = []
    for c, w in TRI_WEIGHTS.items():
        v = float(r[c])
        parts.append({"score": c, "label": label(c), "value": int(v), "level": r[f"{c}_Level"], "weight": w,
                      "points": round(v * w, 2), "vs_average": round((v - mu[c]) * w, 2),
                      "riskier_than_pct": riskier_than(c, v)})
    parts.sort(key=lambda p: -p["vs_average"])
    raw = sum(int(r[c]) * round(w * 100) for c, w in TRI_WEIGHTS.items()) / 100
    ops = []
    for c in OPS:
        v = float(r[c])
        ops.append({"metric": c, "value": v, "average": round(float(mu[c]), 2), "riskier_than_pct": riskier_than(c, v)})
    return {
        "id": sid, "name": r["Supplier Name"], "total_risk_index": int(r["Total_Risk_Index"]),
        "level": r["Total_Risk_Index_Level"], "riskier_than_pct": float(r["TRI_Percentile"]),
        "dataset_average_tri": round(float(mu["Total_Risk_Index"]), 1),
        "formula": "Total_Risk_Index = round(sum(score x weight)) over 18 scores",
        "recomputed": round(raw, 2),
        "drivers_up": [p for p in parts if p["vs_average"] > 0.5][:6],
        "drivers_down": sorted([p for p in parts if p["vs_average"] < -0.5], key=lambda p: p["vs_average"])[:4],
        "contributions": parts,
        "critical_scores": [p["label"] for p in parts if p["level"] == "Critical"],
        "operational_metrics": ops,
        "sourcing_risk_level": r["Sourcing Risk Level"], "supply_chain_complexity": r["Supply Chain Complexity"],
    }


def narrative(sid: str) -> str:
    """Plain-language explanation of a TRI, no LLM needed."""
    e = explain(sid)
    ups = ", ".join(f"{p['label']} {p['value']} (+{p['vs_average']:.1f} pts)" for p in e["drivers_up"][:4])
    downs = ", ".join(f"{p['label']} {p['value']} ({p['vs_average']:.1f})" for p in e["drivers_down"][:2])
    high = e["total_risk_index"] >= e["dataset_average_tri"]
    rel = (f"riskier than {e['riskier_than_pct']:.0f}%" if high else
           f"safer than {int(100 - e['riskier_than_pct'] - (df()['Total_Risk_Index'] == e['total_risk_index']).mean() * 100)}%")
    text = (f"**{e['id']}** has a Total Risk Index of **{e['total_risk_index']}** ({e['level']}), {rel} of the "
            f"10,000 suppliers (average {e['dataset_average_tri']}). ")
    if high:
        text += (f"The index is pushed up mainly by {ups}. " if ups else "") + (f"Partly offset by {downs}. " if downs else "")
    else:
        text += (f"It is kept low mainly by {downs}. " if downs else "") + (f"Weak spots: {ups}. " if ups else "")
    if e["critical_scores"]:
        text += f"Critical-level scores: {', '.join(e['critical_scores'])}."
    return text


# ---------- query & compare ----------

OPS_MAP = {"<": np.less, "<=": np.less_equal, ">": np.greater, ">=": np.greater_equal,
           "==": np.equal, "=": np.equal, "!=": np.not_equal}


def query(conditions: list[dict] | None = None, sort_by: str = "Total_Risk_Index", ascending: bool = True,
          limit: int = 20, base: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[str], int]:
    """Filter with conditions [{column, op, value}] (op: < <= > >= == != in contains).
    Returns (top rows, warnings, total matches)."""
    d = df() if base is None else base
    warn = []
    for c in conditions or []:
        col = resolve_column(c.get("column", ""))
        op, val = c.get("op", "=="), c.get("value")
        if not col:
            warn.append(f"unknown column '{c.get('column')}'")
            continue
        s = d[col]
        if op == "in":
            vals = val if isinstance(val, list) else [val]
            d = d[s.astype(str).str.lower().isin([str(v).lower() for v in vals])]
        elif op == "contains":
            d = d[s.astype(str).str.contains(str(val), case=False, regex=False)]
        elif op in OPS_MAP:
            if pd.api.types.is_numeric_dtype(s):
                d = d[OPS_MAP[op](s, float(val))]
            else:
                d = d[OPS_MAP[op](s.astype(str).str.lower(), str(val).lower())]
        else:
            warn.append(f"unknown op '{op}'")
    sort_col = resolve_column(sort_by) or "Total_Risk_Index"
    d = d.sort_values(sort_col, ascending=ascending)
    return d.head(max(1, min(int(limit), 100))), warn, len(d)


def compare(ids: list[str], columns: list[str] | None = None) -> dict:
    """Side-by-side values, rank within the set and best/worst supplier per column."""
    cols = [resolve_column(c) for c in columns] if columns else ["Total_Risk_Index"] + SCORES + OPS
    cols = [c for c in cols if c]
    d = df().loc[ids]
    out = {"suppliers": ids, "columns": {}}
    for c in cols:
        if c in CATEGORICAL or c == "Supplier Name":
            out["columns"][c] = d[c].to_dict()
            continue
        better_high = c in HIGHER_IS_BETTER
        best = d[c].idxmax() if better_high else d[c].idxmin()
        worst = d[c].idxmin() if better_high else d[c].idxmax()
        if c == PO:  # exposure, not a risk score: report but don't judge
            best = worst = None
        out["columns"][c] = {"values": {k: (float(v) if c in OPS else int(v)) for k, v in d[c].items()},
                             "lowest_risk": best, "highest_risk": worst,
                             "tied": bool(d[c].duplicated(keep=False).any())}
    return out


def similar_lower_risk(sid: str, n: int = 5) -> pd.DataFrame:
    """Swap candidates: same sourcing risk level and complexity, similar PO volume, clearly lower TRI."""
    d = df()
    r = d.loc[sid]
    cand = d[(d["Sourcing Risk Level"] == r["Sourcing Risk Level"]) &
             (d["Supply Chain Complexity"] == r["Supply Chain Complexity"]) &
             (d["Total_Risk_Index"] <= r["Total_Risk_Index"] - 10)].copy()
    cand["_dist"] = (np.log10(cand[PO]) - np.log10(r[PO])).abs() + cand["Total_Risk_Index"] / 100
    return cand.sort_values("_dist").head(n).drop(columns="_dist")


def summary(d: pd.DataFrame | None = None) -> dict:
    d = df() if d is None else d
    return {"suppliers": len(d), "avg_tri": round(float(d["Total_Risk_Index"].mean()), 1) if len(d) else 0,
            "critical": int((d["Total_Risk_Index_Level"] == "Critical").sum()),
            "high": int((d["Total_Risk_Index_Level"] == "High").sum()),
            "po_volume": float(d[PO].sum())}


def stats(column: str, group_by: str | None = None, ids: list[str] | None = None) -> dict:
    col = resolve_column(column)
    if not col:
        return {"error": f"unknown column '{column}'"}
    d = df() if not ids else df().loc[ids]
    s = d[col]
    if col in CATEGORICAL or s.dtype == object or pd.api.types.is_string_dtype(s):
        return {"column": col, "counts": s.value_counts().to_dict()}
    out = {"column": col, "count": int(s.count()), "mean": round(float(s.mean()), 2), "median": float(s.median()),
           "min": float(s.min()), "max": float(s.max()), "p10": float(s.quantile(.1)), "p90": float(s.quantile(.9))}
    if f"{col}_Level" in d:
        out["levels"] = d[f"{col}_Level"].value_counts().reindex(LEVELS, fill_value=0).to_dict()
    gb = resolve_column(group_by) if group_by else None
    if gb:
        out["by_" + gb] = d.groupby(gb)[col].mean().round(2).to_dict()
    return out
