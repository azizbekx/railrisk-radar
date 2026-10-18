"""Formatting helpers shared by the UI and the cache pre-warm script."""
import html


def esc(text, quote: bool = True) -> str:
    """HTML-escape untrusted text (LLM output, web titles) before it goes into unsafe_allow_html markup."""
    return html.escape("" if text is None else str(text), quote=quote)


def safe_url(url) -> str:
    """The URL if it is plain http(s), else empty. Use for href attributes and markdown links."""
    u = str(url or "").strip()
    return u if u.lower().startswith(("http://", "https://")) and not any(c in u for c in "\"'<> \n") else ""


def eur(x: float) -> str:
    if abs(x) >= 1e9:
        return f"€{x/1e9:.1f}bn"
    return f"€{x/1e6:.1f}M" if abs(x) >= 1e6 else f"€{x/1e3:.0f}k"


def trace_line(step: dict) -> str:
    """One markdown line per agent step. Rendered with unsafe_allow_html, so every piece of step content
    (LLM thoughts, tool args, search titles, error text) is HTML-escaped; only the markup added here is live."""
    t = step["type"]
    who = f"[{esc(step['supplier'], False)}] " if step.get("supplier") else ""
    if t == "tool_call":
        args = ", ".join(f"{esc(k, False)}={esc(repr(v), False)}" for k, v in step.get("args", {}).items())
        return f"🔧 {who}`{esc(step['name'], False)}`({args})"
    if t == "tool_result":
        return f"&nbsp;&nbsp;↳ {who}{esc(summarize(step.get('name', ''), step['content']), False)}"
    if t == "thought":
        return f"💭 {esc(step['content'], False)}"
    if t == "error":
        return f"⚠️ {esc(step['content'], False)}"
    return esc(step.get("content", ""), False)


def summarize(name: str, c) -> str:
    """One readable line per tool result for the agent trace."""
    if isinstance(c, str):
        return c
    if isinstance(c, dict) and c.get("error"):
        return f"error: {c['error']}"
    try:
        if name == "search_news" and isinstance(c, list):
            return f"{len(c)} articles" + (f", e.g. *{c[0]['title'][:70]}*" if c else "")
        if name == "trace_impact":
            late = sum(1 for p in c["projects"] if p["late_days"] > 0)
            return f"{c['supplier']}: {late} train project(s) late, **{eur(c['total_exposure_eur'])}** exposure"
        if name == "get_supplier":
            return f"{c['profile']['name']}: risk **{c['score']:.0f}** ({c['band']}), {len(c['events'])} news event(s)"
        if name == "find_alternatives" and isinstance(c, list):
            return f"{len(c)} alternative(s)" + (f", best: {c[0]['alternative']} ({c[0]['status']})" if c else "")
        if name == "list_suppliers" and isinstance(c, list):
            return f"{len(c)} supplier(s): " + ", ".join(x["name"].split()[0] for x in c[:6])
        if name == "list_projects" and isinstance(c, list):
            return f"{len(c)} train projects"
        if name == "find_suppliers":
            ids = ", ".join(x["supplierID"] for x in c["suppliers"][:4])
            return f"{c['total_matches']:,} match(es), top: {ids}" + (f" · {'; '.join(c['warnings'])}" if c["warnings"] else "")
        if name == "get_suppliers":
            return ", ".join(f"{x['supplierID']} TRI {x['Total_Risk_Index']}" for x in c["suppliers"][:6])
        if name == "explain_risk":
            ups = ", ".join(f"{p['label']} +{p['vs_average']:.1f}" for p in c["drivers_up"][:3])
            return f"{c['id']}: TRI **{c['total_risk_index']}** ({c['level']}), main drivers {ups}"
        if name == "compare_suppliers":
            return f"{len(c['suppliers'])} suppliers × {len(c['columns'])} columns"
        if name == "column_stats":
            return f"{c['column']}: mean {c['mean']}" if "mean" in c else f"{c['column']}: {c.get('counts')}"
        if name == "show_chart":
            return f"chart `{c['rendered']}` for {', '.join(c['suppliers']) or 'all suppliers'}"
        if name == "add_to_shortlist":
            return f"added {', '.join(c['added'])} to the shortlist"
    except (KeyError, TypeError, IndexError):
        pass
    n = len(c) if isinstance(c, (list, dict)) else 0
    return f"{n} items returned"
