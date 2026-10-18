"""Agent workflows: news scan, what-if scenario, mitigation plan, live due diligence."""
import json
import time
from concurrent.futures import ThreadPoolExecutor

from core import llm, model as m
from core.agent import load_events, save_events

EVENT_TYPES = "financial, geopolitical, operational, natural_disaster, labour, regulatory, cyber, raw_material, logistics, quality, esg"


def _profile(s: dict) -> str:
    comps = ", ".join(c["component"] for c in m.components_of(s["id"])) or f"tier-2 part feeding {', '.join(s['feeds'])}"
    return (f"{s['name']} ({s['id']}), {s['city']}, {m.country_risk()[s['country']]['name']}. "
            f"Makes: {s['category']}. Supplies: {comps}.")


# ---------- 1. news scan ----------

SCAN_SYSTEM = f"""You are a supply chain risk analyst for Siemens Mobility rolling stock. You receive a supplier
profile and recent news results about the supplier's region, industry and raw materials. The supplier itself is
small, so judge which news items create real exposure for a supplier with this profile and location.
Return JSON only:
{{"summary": "one sentence on the supplier's external risk picture",
  "events": [{{"title": "...", "type": "one of: {EVENT_TYPES}", "severity": 1-5, "confidence": 0-1,
              "relevance": 0-1, "summary": "why this matters for this supplier and for train production",
              "url": "source url", "date": "YYYY-MM-DD or empty"}}]}}
Only include items with relevance >= 0.3. Severity 5 = could stop production for weeks. An empty list is fine."""


def scan_supplier(sid: str, log=None) -> dict:
    s = m.suppliers()[sid]
    queries = [s["search_keywords"], f"{s['category']} supply shortage {m.country_risk()[s['country']]['name']} 2026"]
    results, seen = [], set()
    for q in queries:
        if log:
            log({"type": "tool_call", "name": "search_news", "args": {"query": q}, "supplier": s["name"]})
        try:
            for r in llm.search_news(q, days=90, max_results=5):
                if r["url"] not in seen:
                    seen.add(r["url"])
                    results.append(r)
        except Exception as e:
            if log:
                log({"type": "error", "content": f"search failed: {e}"})
    if not results:
        return {"summary": "No recent news found.", "events": [], "sources": 0, "scanned_at": time.strftime("%Y-%m-%d %H:%M")}
    news = "\n\n".join(f"[{i+1}] {r['title']} ({r['date']})\n{r['url']}\n{r['content']}" for i, r in enumerate(results))
    data = llm.ask_json(SCAN_SYSTEM, f"SUPPLIER: {_profile(s)}\n\nNEWS:\n{news}")
    events = [e for e in data.get("events", []) if float(e.get("relevance", 0)) >= 0.3]
    out = {"summary": data.get("summary", ""), "events": events, "sources": len(results),
           "scanned_at": time.strftime("%Y-%m-%d %H:%M")}
    if log:
        log({"type": "tool_result", "name": "extract_events", "supplier": s["name"],
             "content": f"{len(events)} risk event(s) from {len(results)} articles"})
    return out


def scan_many(sids: list[str], log=None, workers: int = 6) -> dict:
    events = load_events()

    def one(sid):
        try:
            return sid, scan_supplier(sid, log)
        except Exception as e:
            if log:
                log({"type": "error", "content": f"{sid}: {e}"})
            return sid, None

    with ThreadPoolExecutor(workers) as ex:
        for sid, res in ex.map(one, sids):
            if res is not None:
                events[sid] = res
    save_events(events)
    return events


# ---------- 2. what-if scenario ----------

SCENARIO_SYSTEM = """You map a disruption scenario onto a rolling stock supplier base. Given the scenario text and
the supplier list, identify which suppliers are hit directly (by location, region, industry, or raw material).
Return JSON only:
{"title": "short headline", "type": "event type", "location": "place", "lat": number, "lon": number,
 "duration_weeks": number, "explanation": "2 sentences on the mechanism",
 "matched": [{"id": "S..", "capacity_loss": 0-1, "reason": "why this supplier is hit"}]}
Be selective: only suppliers with a plausible direct link. Duration is how long output is disrupted."""


def scenario(text: str) -> dict:
    roster = "\n".join(f"{s['id']} | {s['name']} | {s['city']}, {s['country']} | {s['category']} | tier {s['tier']}"
                       for s in m.suppliers().values())
    data = llm.ask_json(SCENARIO_SYSTEM, f"SCENARIO: {text}\n\nSUPPLIERS:\n{roster}")
    weeks = float(data.get("duration_weeks") or 4)
    impacts, per_project = [], {}
    for hit in data.get("matched", []):
        if hit.get("id") not in m.suppliers():
            continue
        imp = m.trace_impact(hit["id"], weeks, float(hit.get("capacity_loss", 1.0)))
        imp["reason"] = hit.get("reason", "")
        impacts.append(imp)
        for p in imp["projects"]:
            cur = per_project.get(p["project"])
            if cur is None or p["late_days"] > cur["late_days"]:
                per_project[p["project"]] = dict(p)
    projects = sorted(per_project.values(), key=lambda p: -p["exposure_eur"])
    data.update({"impacts": impacts, "projects": projects,
                 "total_exposure_eur": sum(p["exposure_eur"] for p in projects)})
    return data


# ---------- 3. mitigation ----------

MITIGATION_SYSTEM = """You are a senior procurement risk manager at Siemens Mobility. Given a supplier risk profile,
impact analysis and alternative sources, write a mitigation plan. Respect rail realities: requalifying a supplier
takes months, certification (EN 15085-2, EN 45545-2, ISO/TS 22163) cannot be skipped, safety stock costs money.
Return JSON only:
{"headline": "one sentence", "actions": [{"action": "...", "horizon": "now|30 days|90 days|12 months",
 "owner": "role", "effect": "what it reduces, quantified if possible"}],
 "email": {"to": "supplier contact role", "subject": "...", "body": "polite, specific email from Siemens Mobility procurement"}}
4-6 actions."""


def mitigation(sid: str, disruption_weeks: float = 6) -> dict:
    s = m.suppliers()[sid]
    from core.agent import events_for
    sc = m.score_supplier(sid, events_for(sid))
    imp = m.trace_impact(sid, disruption_weeks)
    imp.pop("edges", None)
    comps = [c["component"] for c in m.components_of(sid)] or [s["category"]]
    alts = {c: m.find_alternatives(c) for c in comps + [s["category"]]}
    payload = {"supplier": _profile(s), "score": sc["score"], "reasons": sc["reasons"],
               "events": events_for(sid), "impact": imp, "alternatives": alts}
    return llm.ask_json(MITIGATION_SYSTEM, json.dumps(payload, default=str))


# ---------- 4. live due diligence on a real company ----------

DD_PLAN = """You are a supplier due diligence researcher. Given a company name and first search results, propose
up to 3 follow-up web search queries that would close the biggest gaps (financial health, sanctions/ownership,
litigation, disruptions, ESG/forced labour, rail certifications). Return JSON only: {"queries": ["..."]}"""

DD_REPORT = """You write supplier risk due diligence reports for Siemens Mobility rolling stock procurement.
Use ONLY the provided sources; if evidence is missing say so. Return JSON only:
{"company": "...", "overview": "2-3 sentences: what they make, where, size",
 "score": 0-100 (higher = riskier), "band": "low|watch|act now",
 "factors": [{"name": "Financial|Geopolitical & sanctions|Operational disruption|Legal & compliance|ESG|Rail relevance",
              "score": 0-100, "finding": "one or two sentences", "sources": ["url"]}],
 "red_flags": ["..."], "recommendation": "2-3 sentences: onboard / onboard with conditions / avoid, and next steps"}"""


def due_diligence(company: str, log=None) -> dict:
    def say(step):
        if log:
            log(step)

    base = [f"{company} financial results debt insolvency 2026",
            f"{company} sanctions lawsuit investigation fine",
            f"{company} factory fire strike production disruption",
            f"{company} forced labour environmental violation ESG"]
    sources, seen = [], set()

    def gather(queries):
        with ThreadPoolExecutor(4) as ex:
            for q, res in zip(queries, ex.map(lambda q: _safe_search(q), queries)):
                say({"type": "tool_call", "name": "search_web", "args": {"query": q}})
                fresh = [r for r in res if r["url"] not in seen]
                for r in fresh:
                    seen.add(r["url"])
                    sources.append(r)
                say({"type": "tool_result", "name": "search_web", "content": f"{len(fresh)} new sources"})

    gather(base)
    digest = "\n".join(f"- {r['title']} ({r['url']})" for r in sources[:20])
    try:
        plan = llm.ask_json(DD_PLAN, f"COMPANY: {company}\nFIRST RESULTS:\n{digest}")
        follow = [q for q in plan.get("queries", []) if isinstance(q, str)][:3]
    except Exception:
        follow = []
    if follow:
        say({"type": "thought", "content": "Follow-up research to close gaps: " + "; ".join(follow)})
        gather(follow)
    corpus = "\n\n".join(f"[{i+1}] {r['title']}\n{r['url']}\n{r['content']}" for i, r in enumerate(sources[:24]))
    say({"type": "thought", "content": f"Writing report from {min(len(sources), 24)} sources"})
    report = llm.ask_json(DD_REPORT, f"COMPANY: {company}\n\nSOURCES:\n{corpus}", max_tokens=3500)
    report["source_count"] = len(sources)
    return report


def _safe_search(q):
    try:
        return llm.search_web(q, max_results=5)
    except Exception:
        return []
