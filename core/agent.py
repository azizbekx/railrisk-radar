"""Tool-calling agent loop (Nemotron) with a visible reasoning trace."""
import json
from pathlib import Path

from core import llm, model as m

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


TOOLS = {
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


def run(question: str, history: list | None = None, max_steps: int = 8, tools=None):
    """Generator yielding trace steps: {'type': 'tool_call'|'tool_result'|'thought'|'answer'|'error', ...}."""
    msgs = [{"role": "system", "content": SYSTEM}] + (history or []) + [{"role": "user", "content": question}]
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
                                    for c in calls]})
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
