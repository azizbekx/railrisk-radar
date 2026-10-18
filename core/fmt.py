"""Formatting helpers shared by the UI and the cache pre-warm script."""


def eur(x: float) -> str:
    return f"€{x/1e6:.1f}M" if abs(x) >= 1e6 else f"€{x/1e3:.0f}k"


def trace_line(step: dict) -> str:
    t = step["type"]
    who = f"[{step['supplier']}] " if step.get("supplier") else ""
    if t == "tool_call":
        args = ", ".join(f"{k}={v!r}" for k, v in step.get("args", {}).items())
        return f"🔧 {who}`{step['name']}`({args})"
    if t == "tool_result":
        return f"&nbsp;&nbsp;↳ {who}{summarize(step.get('name', ''), step['content'])}"
    if t == "thought":
        return f"💭 {step['content']}"
    if t == "error":
        return f"⚠️ {step['content']}"
    return step.get("content", "")


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
    except (KeyError, TypeError, IndexError):
        pass
    n = len(c) if isinstance(c, (list, dict)) else 0
    return f"{n} items returned"
