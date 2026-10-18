"""Agent workflows: news scan, what-if scenario, mitigation plan, live due diligence."""
import json
import re
import time

from core import dataset as ds, llm, model as m
from core.llm import ContextPool as ThreadPoolExecutor  # workers keep the session's model choice
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


def _roster() -> str:
    return "\n".join(f"{s['id']} | {s['name']} | {s['city']}, {s['country']} | {s['category']} | tier {s['tier']}"
                     for s in m.suppliers().values())


def scenario(text: str, log=None) -> dict:
    say = log or (lambda _: None)
    say({"type": "thought", "content": f"Mapping the scenario onto {len(m.suppliers())} suppliers in 22 countries"})
    data = llm.ask_json(SCENARIO_SYSTEM, f"SCENARIO: {text}\n\nSUPPLIERS:\n{_roster()}")
    weeks = float(data.get("duration_weeks") or 4)
    say({"type": "tool_result", "name": "map_scenario",
         "content": f"{data.get('title', 'Event')}: {len(data.get('matched', []))} supplier(s) hit directly, ~{weeks:g} weeks"})
    impacts, per_project = [], {}
    for hit in data.get("matched", []):
        if hit.get("id") not in m.suppliers():
            continue
        say({"type": "tool_call", "name": "trace_impact",
             "args": {"supplier": m.suppliers()[hit["id"]]["name"], "weeks": weeks, "capacity_loss": hit.get("capacity_loss", 1.0)}})
        imp = m.trace_impact(hit["id"], weeks, float(hit.get("capacity_loss", 1.0)))
        imp["reason"] = hit.get("reason", "")
        say({"type": "tool_result", "name": "trace_impact",
             "content": f"{len(imp['components'])} component(s) → {sum(1 for p in imp['projects'] if p['late_days'] > 0)} train project(s) late, €{imp['total_exposure_eur']/1e6:.1f}M"})
        impacts.append(imp)
        for p in imp["projects"]:
            cur = per_project.get(p["project"])
            if cur is None or p["late_days"] > cur["late_days"]:
                per_project[p["project"]] = dict(p)
    projects = sorted(per_project.values(), key=lambda p: -p["exposure_eur"])
    data.update({"impacts": impacts, "projects": projects,
                 "total_exposure_eur": sum(p["exposure_eur"] for p in projects)})
    return data


THREATS_SYSTEM = """You monitor world news for a rolling stock manufacturer's supply chain. Given recent headlines and the
supplier roster, pick the 4 headlines most likely to disrupt THESE suppliers (location, industry, raw materials,
trade policy). Return JSON only:
{"threats": [{"headline": "short", "scenario": "one-sentence disruption scenario to simulate, with place and duration",
  "suppliers": ["S.."], "url": "source url", "why": "one sentence"}]}"""


def headline_threats(log=None) -> list[dict]:
    say = log or (lambda _: None)
    queries = ["supply chain disruption factory shutdown this week",
               "export controls rare earth semiconductors 2026",
               "port strike flood earthquake manufacturing Europe Asia",
               "steel foundry insolvency energy prices Europe"]
    news, seen = [], set()
    with ThreadPoolExecutor(4) as ex:
        for q, res in zip(queries, ex.map(lambda q: llm.search_news(q, days=14, max_results=6), queries)):
            say({"type": "tool_call", "name": "search_news", "args": {"query": q, "days": 14}})
            fresh = [r for r in res if r["url"] not in seen]
            seen.update(r["url"] for r in fresh)
            news += fresh
            say({"type": "tool_result", "name": "search_news", "content": f"{len(fresh)} new headlines"})
    say({"type": "thought", "content": f"Ranking {len(news)} headlines against the supplier base"})
    digest = "\n".join(f"- {r['title']} ({r['date']}) {r['url']}\n  {r['content'][:250]}" for r in news[:28])
    data = llm.ask_json(THREATS_SYSTEM, f"HEADLINES:\n{digest}\n\nSUPPLIERS:\n{_roster()}")
    return data.get("threats", [])[:4]


def response_prompt(sc: dict) -> str:
    hits = "; ".join(f"{i['supplier']} ({i['supplier_id']}, capacity loss {i['capacity_loss']:.0%}, €{i['total_exposure_eur']/1e6:.1f}M)"
                     for i in sc["impacts"])
    late = "; ".join(f"{p['name']} {p['late_days']} days late, €{p['exposure_eur']/1e6:.1f}M" for p in sc["projects"] if p["late_days"])
    return (f"Disruption: {sc.get('title')}. {sc.get('explanation', '')} Duration ~{sc.get('duration_weeks')} weeks.\n"
            f"Suppliers hit: {hits}.\nTrain projects late: {late or 'none'}.\n"
            "Build a response plan. Use tools: check each hit supplier's profile, find alternatives for the affected "
            "components, and check one recent news item if useful. Then give a ranked action list (owner, horizon, "
            "€ or days saved) and a 2-line message for the Siemens Mobility board.")


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


# ---------- 5. research agent: plan → search → read → dig into red flags → cited report ----------

AREAS = ["Financial & credit", "Legal, compliance & governance", "Operations, quality & supply chain",
         "Safety, labour & ESG", "Cyber & digital", "Geopolitical & location", "Media & reputation"]

RESEARCH_PLAN = f"""You plan supplier due diligence research for a rail procurement buyer at Siemens.
Given a company name, write a research plan. Return JSON only:
{{"entity": "full legal name if known, else the name given", "hypothesis": "one sentence on what the company
likely is (industry, HQ) and which risks to expect",
 "queries": [{{"area": "one of: {', '.join(AREAS)}", "query": "web search query", "why": "short"}}]}}
6-8 queries, at least one per area that matters most for a train component supplier. Put the company name in each query."""

RESEARCH_TRIAGE = """You review first-pass research on a potential supplier and decide where to dig deeper.
Return JSON only: {"red_flags": [{"flag": "short title", "severity": 1-5, "area": "...", "evidence": "what the
sources say", "follow_up": ["1-2 precise search queries to confirm, date and size the issue"]}],
"gaps": [{"area": "important area with no evidence yet", "query": "precise web search query to fill it"}]}
Only list flags that sources actually hint at (insolvency, fines, sanctions, lawsuits, recalls, fatal accidents,
strikes, cyber attacks, plant shutdowns, forced labour, ownership by sanctioned entities, profit warnings...).
Severity 5 = could stop supply or bar us legally. Up to 4 flags, highest severity first. An empty list is fine."""

SCORE_KEYS = ", ".join(f'"{s}"' for s in ds.SCORES)

RESEARCH_REPORT = f"""You write supplier risk reports for Siemens rail procurement. Use ONLY the numbered sources.
Score the company on the same 18 risk dimensions as the buyer's supplier dataset (0 = no risk, 100 = maximum risk;
levels Low <25, Medium 25-49, High 50-74, Critical >=75). Use null when sources give no evidence for a dimension:
never invent. Cite sources by number. Return JSON only:
{{"company": "...", "website": "url or empty", "overview": "2-3 sentences: what they make, where, size, ownership",
 "scores": {{<each of {SCORE_KEYS}>: {{"score": 0-100 or null, "evidence": "one sentence", "sources": [n]}}}},
 "red_flags": [{{"title": "...", "severity": 1-5, "detail": "what happened, when, how big", "status": "confirmed|unconfirmed|resolved", "sources": [n]}}],
 "strengths": ["short, with [n] citations"],
 "verdict": "approve|approve with conditions|escalate|reject",
 "recommendation": "3-4 sentences for the buyer: decision, conditions, what to ask the supplier"}}"""


def _domain(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0]


def research_company(company: str, log=None, max_flags: int = 3) -> dict:
    say = log or (lambda _: None)
    sources, seen = [], set()

    def add(results, area=""):
        fresh = []
        for r in results:
            if r.get("url") and r["url"] not in seen:
                seen.add(r["url"])
                r = {**r, "area": area, "n": len(sources) + 1}
                sources.append(r)
                fresh.append(r)
        return fresh

    def search_batch(queries):
        def one(q):
            res = _safe_search(q["query"])
            if q.get("news"):
                try:
                    res += llm.search_news(q["query"], days=365, max_results=4)
                except Exception:
                    pass
            return res
        with ThreadPoolExecutor(6) as ex:
            for q, res in zip(queries, ex.map(one, queries)):
                say({"type": "tool_call", "name": "search_web", "args": {"query": q["query"]}})
                fresh = add(res, q.get("area", ""))
                say({"type": "tool_result", "name": "search_web",
                     "content": f"{len(fresh)} new source(s)" + (f", e.g. *{fresh[0]['title'][:70]}*" if fresh else "")})

    def read_pages(urls, why):
        urls = [u for u in urls if u][:3]
        if not urls:
            return
        say({"type": "tool_call", "name": "read_pages", "args": {"urls": [_domain(u) for u in urls], "why": why}})
        try:
            res = llm.tavily().extract(urls=urls, extract_depth="basic").get("results", [])
        except Exception as e:
            say({"type": "error", "content": f"page read failed: {e}"})
            return
        for page in res:
            text = (page.get("raw_content") or "")[:3500]
            for s in sources:
                if s["url"] == page.get("url"):
                    s["content"] = text
                    break
            else:
                add([{"title": _domain(page.get("url", "")), "url": page.get("url"), "content": text}], why)
        say({"type": "tool_result", "name": "read_pages", "content": f"read {len(res)} page(s) in full"})

    # 1. plan
    say({"type": "thought", "content": f"Planning research on **{company}**"})
    try:
        plan = llm.ask_json(RESEARCH_PLAN, f"COMPANY: {company}")
    except Exception as e:
        say({"type": "error", "content": f"planning failed, using default plan: {e}"})
        plan = {"entity": company, "hypothesis": "", "queries": []}
    queries = [q for q in plan.get("queries", []) if isinstance(q, dict) and q.get("query")][:8]
    if not queries:
        queries = [{"area": a, "query": f"{company} {a.split(',')[0].lower()} risk"} for a in AREAS]
    queries.append({"area": "Overview", "query": f"{company} official website company profile headquarters products"})
    queries.append({"area": "Media & reputation", "query": f"{company} news", "news": True})
    say({"type": "thought", "content": "Research plan: " + "; ".join(f"*{q['area']}*: {q['query']}" for q in queries[:8])})

    # 2. broad search
    search_batch(queries)

    # 3. read the company's own site
    token = re.sub(r"[^a-z0-9]", "", company.lower().split()[0])
    own = [s["url"] for s in sources if token and token in _domain(s["url"]).replace("-", "").replace(".", "")]
    read_pages(own[:2], "company website")

    # 4. triage and dig deeper on red flags
    digest = "\n".join(f"[{s['n']}] ({s.get('area', '')}) {s['title']} | {_domain(s['url'])}\n    {(s.get('content') or '')[:300]}"
                       for s in sources[:40])
    try:
        tri = llm.ask_json(RESEARCH_TRIAGE, f"COMPANY: {company}\n\nSOURCES:\n{digest}")
    except Exception as e:
        say({"type": "error", "content": f"triage failed: {e}"})
        tri = {"red_flags": [], "gaps": []}
    flags = sorted([f for f in tri.get("red_flags", []) if isinstance(f, dict)],
                   key=lambda f: -float(f.get("severity", 0) or 0))
    if flags:
        say({"type": "thought", "content": "🚩 Red flags to verify: " +
             "; ".join(f"**{f.get('flag')}** (severity {f.get('severity')})" for f in flags)})
        deep = [{"area": f.get("area", ""), "query": q, "news": True}
                for f in flags[:max_flags] for q in (f.get("follow_up") or [])[:2] if isinstance(q, str)]
        before = len(sources)
        search_batch(deep)
        # read the strongest new evidence in full
        read_pages([s["url"] for s in sources[before:before + 3]], "red-flag evidence")
    else:
        say({"type": "thought", "content": "No red flags in first pass"})
    gaps = [g for g in tri.get("gaps", []) if isinstance(g, dict) and g.get("query")][:2]
    if gaps:
        say({"type": "thought", "content": "Closing evidence gaps: " + ", ".join(g.get("area", "") for g in gaps)})
        search_batch([{"area": g.get("area", ""), "query": g["query"] if company.lower() in g["query"].lower()
                       else f"{company} {g['query']}"} for g in gaps])

    # 5. report
    corpus = "\n\n".join(f"[{s['n']}] {s['title']} ({s.get('date', '')})\n{s['url']}\n{(s.get('content') or '')[:1500]}"
                         for s in sources[:45])
    say({"type": "thought", "content": f"Writing the cited report from {min(len(sources), 45)} sources"})
    rep = llm.ask_json(RESEARCH_REPORT, f"COMPANY: {company}\nRESEARCH FLAGS: {json.dumps(flags)}\n\nSOURCES:\n{corpus}",
                       max_tokens=6000)
    return finalize_report(rep, sources, plan, flags)


def finalize_report(rep: dict, sources: list[dict], plan: dict, flags: list) -> dict:
    """Turn the LLM report into a dataset-comparable risk profile with an index computed by the dataset's own formula."""
    scores = rep.get("scores") or {}
    mu = ds.means()
    filled, known_w = {}, 0.0
    for c, w in ds.TRI_WEIGHTS.items():
        v = (scores.get(c) or {}).get("score") if isinstance(scores.get(c), dict) else None
        if isinstance(v, (int, float)):
            filled[c] = max(0.0, min(100.0, float(v)))
            known_w += w
        else:
            filled[c] = float(mu[c])  # no evidence: assume dataset average, shown as unknown
    tri = round(sum(filled[c] * w for c, w in ds.TRI_WEIGHTS.items()))
    rep.update({"total_risk_index": tri, "level": ds.level(tri), "evidence_coverage": round(known_w, 2),
                "riskier_than_pct": ds.riskier_than("Total_Risk_Index", tri), "filled_scores": filled,
                "sources": [{"n": s["n"], "title": s["title"], "url": s["url"], "area": s.get("area", "")} for s in sources],
                "plan": plan, "triage_flags": flags, "researched_at": time.strftime("%Y-%m-%d %H:%M")})
    return rep


def report_markdown(rep: dict) -> str:
    src = {s["n"]: s for s in rep.get("sources", [])}

    def cite(ns):
        return " ".join(f"[[{n}]]({src[n]['url']})" for n in ns or [] if n in src)

    lines = [f"# Supplier risk report: {rep.get('company', '')}", "",
             f"*Researched {rep.get('researched_at', '')} · {len(src)} sources · verdict: **{rep.get('verdict', '')}***", "",
             rep.get("overview", ""), "",
             f"**Total Risk Index (dataset formula): {rep['total_risk_index']} ({rep['level']})**, riskier than "
             f"{rep['riskier_than_pct']:.0f}% of the 10,000 suppliers in the dataset. Evidence covers "
             f"{rep['evidence_coverage']:.0%} of the index weight; dimensions without evidence are set to the dataset average.", "",
             "## Recommendation", rep.get("recommendation", ""), "", "## Red flags"]
    for f in rep.get("red_flags", []) or ["none found"]:
        if isinstance(f, dict):
            lines.append(f"- **{f.get('title')}** (severity {f.get('severity')}/5, {f.get('status', '')}): {f.get('detail', '')} {cite(f.get('sources'))}")
        else:
            lines.append(f"- {f}")
    lines += ["", "## Strengths"] + [f"- {s}" for s in rep.get("strengths", [])]
    lines += ["", "## Risk dimensions", "", "| Dimension | Score | Evidence |", "|---|---|---|"]
    for c in ds.SCORES:
        d = (rep.get("scores") or {}).get(c) or {}
        sc = d.get("score")
        lines.append(f"| {ds.label(c)} | {sc if sc is not None else 'no evidence'} | {d.get('evidence', '')} {cite(d.get('sources'))} |")
    lines += ["", "## Sources"] + [f"{s['n']}. [{s['title']}]({s['url']})" for s in rep.get("sources", [])]
    return "\n".join(lines)


# ---------- 6. shortlist decision memo ----------

MEMO_SYSTEM = """You are a senior rail procurement buyer at Siemens writing a supplier selection memo for the
sourcing committee. Use ONLY the facts given; quote the numbers. Markdown, about one page:
## Recommendation (1-2 sentences: chosen supplier ID and why)
## Why this supplier over the alternatives (bullets with concrete score comparisons vs the runner-ups)
## Risks we accept and how we mitigate them (the chosen supplier's High/Critical scores, each with a concrete
   contractual or operational mitigation for a rail component supplier)
## Alternatives considered (compact markdown table: ID, TRI, lens index, main weakness)
## Next steps (3 bullets)
Scores are 0-100 where higher = riskier. Delivery and confirmation rates: higher = better."""


def memo_facts(chosen: str, ids: list[str], weights: dict, lens_name: str, context: str) -> dict:
    d = ds.df().loc[ids].copy()
    d["lens_index"] = ds.lens_index(d, weights)
    d = d.sort_values("lens_index")
    e = ds.explain(chosen)
    rows = []
    for sid, r in d.iterrows():
        worst = max(ds.SCORES, key=lambda c: r[c])
        rows.append({"id": sid, "TRI": int(r["Total_Risk_Index"]), "level": r["Total_Risk_Index_Level"],
                     "lens_index": float(r["lens_index"]), "rank_by_lens": len(rows) + 1,
                     "delivery_rating": float(r["Supplier Delivery Rating"]),
                     "confirmation_rate": float(r["Order Confirmation Rate"]),
                     "order_change_rate": float(r["Order Change Rate"]), "po_volume_eur": float(r[ds.PO]),
                     "sourcing_risk": r["Sourcing Risk Level"], "complexity": r["Supply Chain Complexity"],
                     "worst_score": f"{ds.label(worst)} {int(r[worst])}",
                     "critical_scores": [ds.label(c) for c in ds.SCORES if r[c] >= 75]})
    return {"buying_context": context or "not given", "risk_lens": lens_name,
            "lens_weights": {ds.label(k): round(v, 3) for k, v in ds.normalize_weights(weights).items()},
            "chosen": chosen, "shortlist_ranked": rows,
            "chosen_breakdown": {k: e[k] for k in ("total_risk_index", "level", "riskier_than_pct", "drivers_up",
                                                     "drivers_down", "critical_scores", "operational_metrics")},
            "head_to_head": ds.compare(list(d.index[:6]) if chosen in d.index[:6] else [chosen] + list(d.index[:5]))}


def shortlist_memo(chosen: str, ids: list[str], weights: dict, lens_name: str, context: str = "") -> str:
    facts = memo_facts(chosen, ids, weights, lens_name, context)
    reply = llm.chat([{"role": "system", "content": MEMO_SYSTEM},
                      {"role": "user", "content": json.dumps(facts, default=str)}], max_tokens=2500)
    header = (f"# Supplier selection memo: {chosen}\n\n*{time.strftime('%d %b %Y')} · shortlist of {len(ids)} · "
              f"risk lens: {lens_name}" + (f" · context: {context}" if context else "") + "*\n\n")
    return header + llm.clean(reply.content)
