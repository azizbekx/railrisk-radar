"""Tool-calling agent loop (Nemotron) with a visible reasoning trace."""
import json
from pathlib import Path

from core import dataset as ds, llm, model as m

CACHE = Path(__file__).resolve().parent.parent / "cache"
CACHE.mkdir(exist_ok=True)
EVENTS_FILE = CACHE / "events.json"


# ---------- shared event store ----------

def load_events() -> dict:
    if EVENTS_FILE.exists():
        return json.loads(EVENTS_FILE.read_text())
    return {}


def save_events(events: dict):
    EVENTS_FILE.write_text(json.dumps(events, indent=2))


def events_for(sid: str) -> list[dict]:
    return load_events().get(sid, {}).get("events", [])


def current_scores() -> list[dict]:
    ev = load_events()
    return m.score_all({k: v.get("events", []) for k, v in ev.items()})


# ---------- tools ----------

def t_list_suppliers(country: str = "", category: str = "", min_score: float = 0, single_source_only: bool = False):
    rows = []
    for r in current_scores():
        s = m.suppliers()[r["id"]]
        if country and country.lower() not in (s["country"].lower(), m.country_risk().get(s["country"], {}).get("name", "").lower()):
            continue
        if category and category.lower() not in s["category"].lower():
            continue
        if r["score"] < min_score or (single_source_only and not m.is_single_source(r["id"])):
            continue
        rows.append({"id": r["id"], "name": s["name"], "country": s["country"], "city": s["city"],
                     "category": s["category"], "tier": s["tier"], "score": r["score"], "band": r["band"],
                     "single_source": m.is_single_source(r["id"]),
                     "components": [c["component"] for c in m.components_of(r["id"])] or [f"(tier 2, feeds {', '.join(s['feeds'])})"]})
    return rows


def t_get_supplier(supplier: str):
    s = m.resolve_supplier(supplier)
    if not s:
        return {"error": f"unknown supplier '{supplier}'. Use list_suppliers first."}
    ev = events_for(s["id"])
    sc = m.score_supplier(s["id"], ev)
    return {"profile": {k: s[k] for k in ("id", "name", "country", "city", "category", "tier", "feeds", "spend_meur",
                                          "financial_score", "quality_ppm", "ncr_12m", "otd_6m", "stock_days",
                                          "lead_time_weeks", "note")},
            "components": m.components_of(s["id"]), "score": sc["score"], "band": sc["band"],
            "factors": sc["factors"], "reasons": sc["reasons"], "certs": sc["certs"],
            "events": [{k: e.get(k) for k in ("title", "type", "severity", "summary", "url")} for e in ev]}


def t_search_news(query: str, days: int = 60):
    return llm.search_news(query, days=days, max_results=5)


def t_trace_impact(supplier: str, disruption_weeks: float = 4, capacity_loss: float = 1.0):
    s = m.resolve_supplier(supplier)
    if not s:
        return {"error": f"unknown supplier '{supplier}'"}
    r = m.trace_impact(s["id"], float(disruption_weeks), float(capacity_loss))
    r.pop("edges", None)
    return r


def t_find_alternatives(component: str):
    return m.find_alternatives(component) or {"result": f"no alternatives on file for '{component}'"}


def t_list_projects():
    return list(m.projects().values())


# ---------- tools over the 10,000-supplier Siemens dataset ----------

KEY_COLS = ["Supplier Name", "Total_Risk_Index", "Total_Risk_Index_Level", "Sourcing Risk Level",
            "Supply Chain Complexity", "Supplier Delivery Rating"]


def _rows(d, extra=()):
    cols = list(dict.fromkeys(["supplierID"] + KEY_COLS + [c for c in extra if c in d.columns]))
    return d[cols].to_dict("records")


def t_find_suppliers(conditions: list | None = None, sort_by: str = "Total_Risk_Index", ascending: bool = True,
                     limit: int = 10, columns: list | None = None):
    rows, warn, total = ds.query(conditions or [], sort_by, ascending, limit)
    extra = [ds.resolve_column(c.get("column", "")) for c in conditions or []] + \
            [ds.resolve_column(sort_by)] + [ds.resolve_column(c) for c in columns or []]
    return {"total_matches": total, "showing": len(rows), "warnings": warn,
            "suppliers": _rows(rows, [c for c in extra if c])}


def t_get_suppliers(suppliers: list | str):
    ids, bad = ds.resolve_many(suppliers)
    out = []
    for sid in ids[:20]:
        r = ds.df().loc[sid]
        out.append({"supplierID": sid, "riskier_than_pct_of_suppliers": float(r["TRI_Percentile"]),
                    **{k: (v.item() if hasattr(v, "item") else v) for k, v in r.drop(["supplierID", "TRI_Percentile"]).items()}})
    return {"suppliers": out, "not_found": bad}


def t_explain_risk(supplier: str):
    sid = ds.resolve(supplier)
    if not sid:
        return {"error": f"no supplier '{supplier}' in the dataset"}
    e = ds.explain(sid)
    e.pop("contributions")
    return e


def t_compare_suppliers(suppliers: list | str, columns: list | None = None):
    ids, bad = ds.resolve_many(suppliers)
    if not ids:
        return {"error": "none of these suppliers exist in the dataset", "not_found": bad}
    return {**ds.compare(ids[:20], columns), "not_found": bad}


def t_column_stats(column: str, group_by: str = "", suppliers: list | None = None):
    ids = ds.resolve_many(suppliers)[0] if suppliers else None
    return ds.stats(column, group_by or None, ids)


def t_show_chart(kind: str, suppliers: list | None = None, columns: list | None = None, title: str = ""):
    ids = ds.resolve_many(suppliers)[0] if suppliers else []
    return {"rendered": kind, "suppliers": ids[:20], "columns": [c for c in (ds.resolve_column(x) for x in columns or []) if c]}


def t_add_to_shortlist(suppliers: list | str):
    ids, bad = ds.resolve_many(suppliers)
    return {"added": ids[:20], "not_found": bad}


COLUMN_HELP = ("Columns: Total_Risk_Index, the 18 risk scores (" + ", ".join(ds.SCORES) +
               "), each with a *_Level column (Low/Medium/High/Critical), Purchase Order Volume (EUR), Order Change Rate, "
               "Supplier Delivery Rating, Order Confirmation Rate, Sourcing Risk Level (Low/Medium/High), "
               "Supply Chain Complexity (Simple/Moderate/Complex), Supplier Name. Loose names like 'financial' work.")

TOOLS = {
    "find_suppliers": (t_find_suppliers, "Filter, sort and rank the 10,000 suppliers. " + COLUMN_HELP,
                       {"conditions": {"type": "array", "description": "filters, ANDed",
                                       "items": {"type": "object", "properties": {
                                           "column": {"type": "string"},
                                           "op": {"type": "string", "enum": ["<", "<=", ">", ">=", "==", "!=", "in", "contains"]},
                                           "value": {"description": "number, string or list for 'in'"}},
                                           "required": ["column", "op", "value"]}},
                        "sort_by": {"type": "string"}, "ascending": {"type": "boolean", "description": "true = lowest first"},
                        "limit": {"type": "integer", "description": "max rows, up to 100"},
                        "columns": {"type": "array", "items": {"type": "string"}, "description": "extra columns to return"}}, []),
    "get_suppliers": (t_get_suppliers, "All columns for up to 20 suppliers by ID (SUPP_00012) or name.",
                      {"suppliers": {"type": "array", "items": {"type": "string"}}}, ["suppliers"]),
    "explain_risk": (t_explain_risk, "Exact breakdown of one supplier's Total_Risk_Index: each score x its weight, which "
                     "scores push it above/below the dataset average, percentiles, operational metrics.",
                     {"supplier": {"type": "string"}}, ["supplier"]),
    "compare_suppliers": (t_compare_suppliers, "Side-by-side values for 2-20 suppliers with lowest/highest risk per column. "
                          "Omit columns to compare everything.",
                          {"suppliers": {"type": "array", "items": {"type": "string"}},
                           "columns": {"type": "array", "items": {"type": "string"}}}, ["suppliers"]),
    "column_stats": (t_column_stats, "Distribution of a column across all suppliers (or a given set), optionally "
                     "averaged by a category column.",
                     {"column": {"type": "string"}, "group_by": {"type": "string"},
                      "suppliers": {"type": "array", "items": {"type": "string"}}}, ["column"]),
    "show_chart": (t_show_chart, "Show the buyer a chart under your answer. kind: 'risk_breakdown' (one supplier, "
                   "why its TRI is what it is), 'compare_bars' (suppliers x a few columns), 'heatmap' (suppliers x all "
                   "scores), 'radar' (2-5 suppliers' risk profiles), 'distribution' (one column across all suppliers, "
                   "marking the given suppliers). Call it once when a visual helps.",
                   {"kind": {"type": "string", "enum": ["risk_breakdown", "compare_bars", "heatmap", "radar", "distribution"]},
                    "suppliers": {"type": "array", "items": {"type": "string"}},
                    "columns": {"type": "array", "items": {"type": "string"}}, "title": {"type": "string"}}, ["kind"]),
    "add_to_shortlist": (t_add_to_shortlist, "Add suppliers to the buyer's comparison shortlist (max 20) when asked.",
                         {"suppliers": {"type": "array", "items": {"type": "string"}}}, ["suppliers"]),
    "list_suppliers": (t_list_suppliers, "List suppliers with current risk score. Optional filters.",
                       {"country": {"type": "string", "description": "ISO code or country name"},
                        "category": {"type": "string", "description": "e.g. 'brake', 'HVAC'"},
                        "min_score": {"type": "number"},
                        "single_source_only": {"type": "boolean"}}, []),
    "get_supplier": (t_get_supplier, "Full risk profile of one supplier: KPIs, score breakdown, certificates, news events.",
                     {"supplier": {"type": "string", "description": "supplier id like S05 or name"}}, ["supplier"]),
    "search_news": (t_search_news, "Search recent news on the web (Tavily). Use for live risk signals.",
                    {"query": {"type": "string"}, "days": {"type": "integer", "description": "look-back window"}}, ["query"]),
    "trace_impact": (t_trace_impact, "Propagate a disruption at a supplier through the BOM to train projects; returns delay days and EUR penalty exposure.",
                     {"supplier": {"type": "string"}, "disruption_weeks": {"type": "number"},
                      "capacity_loss": {"type": "number", "description": "0-1 share of capacity lost"}}, ["supplier"]),
    "find_alternatives": (t_find_alternatives, "Alternative suppliers for a component, with qualification status and time.",
                          {"component": {"type": "string"}}, ["component"]),
    "list_projects": (t_list_projects, "Train projects with delivery dates and contract penalties.", {}, []),
}

DATA_TOOLS = ["find_suppliers", "get_suppliers", "explain_risk", "compare_suppliers", "column_stats",
              "show_chart", "add_to_shortlist"]
RAIL_TOOLS = ["list_suppliers", "get_supplier", "search_news", "trace_impact", "find_alternatives", "list_projects"]


def tool_specs(names=None):
    out = []
    for name, (_, desc, props, req) in TOOLS.items():
        if names and name not in names:
            continue
        out.append({"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}})
    return out


def run_tool(name: str, args: dict):
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    try:
        return TOOLS[name][0](**args)
    except Exception as e:  # surface tool errors to the model instead of crashing
        return {"error": str(e)}


# ---------- loop ----------

SYSTEM = f"""You are RailRisk Radar, a supply chain risk analyst agent for Siemens Mobility rolling stock
(trains, locomotives, metros). Today is {m.TODAY.isoformat()}.
You have tools over the supplier base, the bill of materials of 4 train projects, live news search,
impact tracing and alternative suppliers. Always ground answers in tool results; never invent suppliers or numbers.
Rail context: switching suppliers takes 12-24 months because of certification (EN 15085-2 welding,
EN 45545-2 fire safety, ISO/TS 22163, EN 50155 electronics). Single-sourced long-lead parts are the main danger.
When you finish, answer concisely in markdown: findings first, then quantified impact (days, EUR), then
concrete recommended actions. Cite news URLs when you used them."""


DATA_SYSTEM = f"""You are the supplier selection assistant for Siemens rail procurement buyers. You answer questions
about a dataset of 10,000 anonymized suppliers (IDs like SUPP_00012) using tools. Every number you state must come
from a tool result in this conversation; never guess. If something is not in the data (country, product category,
real company identity) say so plainly.

Facts about the data:
- All risk scores run 0-100, higher = riskier. Levels: Low <25, Medium 25-49, High 50-74, Critical >=75.
- Total_Risk_Index (TRI) is exactly round(sum of the 18 scores x fixed weights): {", ".join(f"{ds.label(k)} {v:.0%}" for k, v in ds.TRI_WEIGHTS.items())}.
  Use explain_risk to say why a TRI is high or low: name the scores that add the most points vs the dataset average.
- Operational metrics are NOT part of TRI: Supplier Delivery Rating and Order Confirmation Rate (higher = better),
  Order Change Rate (higher = worse), Purchase Order Volume (EUR) = financial exposure.
- Sourcing Risk Level = how hard the supplier is to replace (Low = easy to find alternatives, High = hard).
  Supply Chain Complexity = complexity of the supplier's logistics routes and sub-tiers.
- "Financial risk" is ambiguous: Financial_Health_Score and Credit_Rating_Score both measure it. Answer with
  Financial_Health_Score and mention Credit_Rating_Score when it changes the picture.

Style: lead with the direct answer and the supplier ID in bold, then the evidence as a short list or small markdown
table. Keep it under 200 words unless asked for more. Call show_chart once when comparing several suppliers or
explaining a score, so the buyer sees it. Only call add_to_shortlist when the buyer asks."""


def run(question: str, history: list | None = None, max_steps: int = 8, tools=None, system: str = SYSTEM):
    """Generator yielding trace steps: {'type': 'tool_call'|'tool_result'|'thought'|'answer'|'error', ...}."""
    msgs = [{"role": "system", "content": system}] + (history or []) + [{"role": "user", "content": question}]
    specs = tool_specs(tools)
    for step in range(max_steps):
        try:
            msg = llm.chat(msgs, tools=specs, max_tokens=3000)
        except Exception as e:
            yield {"type": "error", "content": f"LLM call failed: {e}"}
            return
        calls = msg.tool_calls or []
        text = llm.clean(msg.content)
        if not calls:
            yield {"type": "answer", "content": text or "(no answer)"}
            return
        if text:
            yield {"type": "thought", "content": text}
        msgs.append({"role": "assistant", "content": msg.content or "",
                     "tool_calls": [{"id": c.id, "type": "function",
                                     "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                                    for c in calls],
                     "_claude_content": getattr(msg, "claude_content", None)})
        for c in calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_call", "name": c.function.name, "args": args}
            result = run_tool(c.function.name, args)
            yield {"type": "tool_result", "name": c.function.name, "content": result}
            msgs.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result, default=str)[:12000]})
    msgs.append({"role": "user", "content": "Stop using tools now and give your final answer from what you have."})
    try:
        yield {"type": "answer", "content": llm.clean(llm.chat(msgs, max_tokens=2500).content)}
    except Exception as e:
        yield {"type": "error", "content": str(e)}
