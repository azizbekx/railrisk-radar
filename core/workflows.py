"""Agent workflows: news scan, what-if scenario, mitigation plan, live due diligence."""
import json
import re
import time
from difflib import SequenceMatcher
from functools import lru_cache
from urllib.parse import urlparse

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


# ---------- 5. research agent: plan → search → read → iterative dig into red flags → cited report ----------

AREAS = ["Financial & credit", "Legal, compliance & governance", "Operations, quality & supply chain",
         "Safety, labour & ESG", "Cyber & digital", "Geopolitical & location", "Media & reputation"]

RESEARCH_PLAN = f"""You plan supplier due diligence research for a rail procurement buyer at Siemens.
Given a company name, write a research plan. Return JSON only:
{{"entity": "full legal name if known, else the name given",
 "website": "your best guess at the official company domain, e.g. example.com (no path), or empty if unsure",
 "hypothesis": "one sentence on what the company likely is (industry, HQ) and which risks to expect",
 "queries": [{{"area": "one of: {', '.join(AREAS)}", "query": "web search query", "why": "short"}}]}}
6-8 queries, at least one per area that matters most for a train component supplier. Put the company name in each query."""

RESEARCH_REVIEW = """You lead supplier due diligence research for Siemens rail procurement and decide where to dig deeper.
You get the red flags found so far (with their current status) and numbered sources. For EVERY flag decide:
- "confirmed": the sources show it happened and give its date or scale (it need not be fully sized; settle it),
- "refuted": the sources show it is wrong, concerns another company, or is fully resolved with no remaining exposure,
- "needs_more": plausible but unverified or unsized; give 1-2 NEW precise search queries (company name, event, year).
You may add new flags the sources hint at (insolvency, fines, sanctions, lawsuits, recalls, fatal accidents, strikes,
cyber attacks, plant shutdowns, forced labour, sanctioned owners, profit warnings...). Keep at most 5 flags, highest
severity first; severity 5 = could stop supply or bar us legally. Only flag what sources actually hint at. A flag is a
concrete adverse event or exposure of THIS company: "no evidence of X" is a gap, and doubts about a source are not flags.
Keep "evidence" under 30 words.
List up to 2 important risk areas that still have no evidence as gaps, each with a precise search query.
Set "done": true when every flag is confirmed or refuted and no important gap remains, or when more searching is
unlikely to change the picture. Return JSON only:
{"flags": [{"id": "the flag's id (e.g. F1) for existing flags, empty for new ones", "flag": "short title",
  "severity": 1-5, "area": "...", "status": "confirmed|refuted|needs_more",
  "evidence": "what the sources say, citing [n]", "sources": [n], "follow_up": ["queries, only when needs_more"]}],
 "gaps": [{"area": "...", "query": "..."}], "done": true or false, "reason": "one sentence"}"""

SCORE_KEYS = ", ".join(f'"{s}"' for s in ds.SCORES)

RESEARCH_REPORT = f"""You write supplier risk reports for Siemens rail procurement. Use ONLY the numbered sources.
Score the company on the same 18 risk dimensions as the buyer's supplier dataset (0 = no risk, 100 = maximum risk;
levels Low <25, Medium 25-49, High 50-74, Critical >=75). Use null when sources give no evidence for a dimension:
never invent. Cite sources by number, only numbers that appear in SOURCES. RESEARCH FLAGS are the agent's verified
findings: list confirmed and unresolved ones as red flags (with their flag_id); do not list refuted ones as red flags.
Return JSON only:
{{"company": "...", "website": "url or empty", "overview": "2-3 sentences: what they make, where, size, ownership",
 "scores": {{<each of {SCORE_KEYS}>: {{"score": 0-100 or null, "evidence": "one sentence", "sources": [n]}}}},
 "red_flags": [{{"flag_id": "F.. or empty", "title": "...", "severity": 1-5, "detail": "what happened, when, how big", "status": "confirmed|unconfirmed|resolved", "sources": [n]}}],
 "strengths": ["short, with [n] citations"],
 "verdict": "approve|approve with conditions|escalate|reject",
 "recommendation": "3-4 sentences for the buyer: decision, conditions, what to ask the supplier"}}"""

MAX_ROUNDS = 3          # dig-deeper rounds after the first triage
MAX_SOURCES = 60        # total source budget per company
CORPUS_CHARS = 60000    # report corpus budget (the old pipeline sent up to ~67k chars)
TIME_BUDGET_S = 240     # no new dig round starts after this many seconds
REVIEW_TIMEOUT_S = 90   # a stalled triage/review call is abandoned, the agent continues with what it has
RESOLUTION = {"confirmed": "confirmed", "refuted": "refuted", "needs_more": "unresolved"}

# words that never identify a company's own domain
_NAME_STOP = {"ag", "sa", "se", "nv", "bv", "ab", "oy", "as", "kg", "kgaa", "gmbh", "mbh", "inc", "ltd", "llc", "plc", "spa",
              "srl", "sas", "sl", "co", "corp", "corporation", "company", "group", "holding", "holdings", "limited", "the",
              "and", "of", "y", "de", "la", "le", "der", "und", "et", "rail", "railway", "railways", "systems", "technologies",
              "technology", "international", "industries", "industrial", "engineering", "solutions", "global", "services",
              "mobility", "transport", "manufacturing", "construcciones", "auxiliar"}
_SITE_PAGE = re.compile(r"about|company|who-we-are|profile|investor|sustainab|esg|certif|quality|complian|annual|report", re.I)


def _domain(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0]


def _host(url: str) -> str:
    h = re.sub(r"^[a-z]+://", "", (url or "").strip().lower()).split("/")[0].split("?")[0].split(":")[0]
    return h[4:] if h.startswith("www.") else h


def _on_site(url: str, site: str) -> bool:
    h = _host(url)
    return bool(site) and (h == site or h.endswith("." + site))


def _label(host: str) -> str:
    """Registrable label of a host: new.abb.com -> abb, knorr-bremse.co.uk -> knorr-bremse."""
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {"co", "com", "ac", "net", "org", "gov"}:
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else host


def _looks_own(host: str, company: str) -> bool:
    """Token heuristic: does this domain look like the company's own site?"""
    words = re.findall(r"[a-z0-9]+", company.lower())
    toks = [w for w in words if w not in _NAME_STOP and len(w) >= 3] or words[:1]
    if not toks:
        return False
    compact = "".join(w for w in words if w not in _NAME_STOP)
    lab = _label(host).replace("-", "")
    return lab == compact or lab in toks or (len(toks[0]) >= 4 and lab.startswith(toks[0])) or lab == "".join(words)


def _safe_search(q, max_results: int = 5):
    try:
        return llm.search_web(q, max_results=max_results)
    except Exception:
        return []


def _site_search(query: str, site: str, max_results: int = 5) -> list[dict]:
    try:
        res = llm.tavily().search(query=query, include_domains=[site], max_results=max_results)
    except Exception:
        return []
    return [{"title": r.get("title"), "url": r.get("url"), "content": (r.get("content") or "")[:900]}
            for r in res.get("results", [])]


def _ask_by(seconds: float, system: str, user: str, **kw):
    """llm.ask_json with a wall-clock limit (raises TimeoutError); a stalled call is left to finish in the background."""
    ex = ThreadPoolExecutor(1)
    fut = ex.submit(llm.ask_json, system, user, **kw)
    ex.shutdown(wait=False)
    return fut.result(timeout=seconds)


def _as_list(x) -> list:
    return x if isinstance(x, list) else [x] if x else []


def _with_company(q: str, company: str) -> str:
    return q if company.lower().split()[0] in q.lower() else f"{company} {q}"


def _digest(sources: list[dict], fresh_from: int = 0, fresh_chars: int = 700, old_chars: int = 160) -> str:
    """Compact source list for the LLM: newer sources (n > fresh_from) get more text."""
    out = []
    for s in sources:
        new = s["n"] > fresh_from
        k = (1400 if s.get("read") else fresh_chars) if new else old_chars
        out.append(f"[{s['n']}] ({s.get('area', '')}) {s['title']} | {_domain(s['url'])}"
                   f"{' | ' + s['date'] if s.get('date') else ''}\n    {(s.get('content') or '')[:k]}")
    return "\n".join(out)


def _corpus(sources: list[dict], limit: int = CORPUS_CHARS) -> tuple[str, int]:
    """Numbered sources for the report prompt within a char budget; full-read pages get more room."""
    parts, total = [], 0
    for s in sources:
        head = f"[{s['n']}] {s['title']} ({s.get('date', '')})\n{s['url']}\n"
        body = (s.get("content") or "")[:2000 if s.get("read") else 600]
        room = limit - total - len(head)
        if room <= 0:
            break
        parts.append(head + body[:room])
        total += len(parts[-1]) + 2
    return "\n\n".join(parts), len(parts)


def research_company(company: str, log=None, max_flags: int = 3, max_rounds: int = MAX_ROUNDS,
                     max_sources: int = MAX_SOURCES, time_budget_s: float = TIME_BUDGET_S) -> dict:
    say = log or (lambda _: None)
    t0 = time.time()
    sources, seen, ran = [], set(), set()
    stats = {"pages_read": 0, "queries": 0, "over_budget": 0}

    def add(results, area="", limit=None, take=None):
        """Add unseen http(s) results as numbered sources, up to `take` new ones and `limit` sources in total."""
        fresh, limit = [], min(limit or max_sources, max_sources)
        for r in results:
            if take is not None and len(fresh) >= take:
                break
            if not r.get("url") or r["url"] in seen or not str(r["url"]).startswith(("http://", "https://")):
                continue
            if len(sources) >= limit:
                stats["over_budget"] += 1
                continue
            seen.add(r["url"])
            r = {**r, "title": r.get("title") or _domain(r["url"]), "area": area, "n": len(sources) + 1}
            sources.append(r)
            fresh.append(r)
        return fresh

    def search_batch(queries, per_query: int = 5, limit: int | None = None) -> dict:
        """Run queries in parallel and share the source budget fairly between them; returns {query: fresh sources}."""
        queries = [q for q in queries if q["query"].lower() not in ran]
        ran.update(q["query"].lower() for q in queries)
        stats["queries"] += len(queries)
        limit = min(limit or max_sources, max_sources)

        def one(q):
            if q.get("site"):
                return _site_search(q["query"], q["site"], per_query)
            res = _safe_search(q["query"], per_query)
            if q.get("news"):
                try:
                    res += llm.search_news(q["query"], days=365, max_results=3)
                except Exception:
                    pass
            return res

        if not queries:
            return {}
        with ThreadPoolExecutor(6) as ex:
            results = list(ex.map(one, queries))
        # pass 1: an equal share of the remaining budget per query (company-site results first);
        # pass 2: leftovers in query order
        share = max(1, -(-(limit - len(sources)) // len(queries)))
        order = sorted(zip(queries, results), key=lambda qr: not qr[0].get("site"))
        found = {q["query"]: add(res, q.get("area", ""), limit, share) for q, res in order}
        for q, res in zip(queries, results):
            found[q["query"]] += add(res, q.get("area", ""), limit)
        for q in queries:
            fresh = found[q["query"]]
            args = {"query": q["query"]} | ({"site": q["site"]} if q.get("site") else {})
            say({"type": "tool_call", "name": "search_web", "args": args})
            say({"type": "tool_result", "name": "search_web",
                 "content": f"{len(fresh)} new source(s)" + (f", e.g. *{fresh[0]['title'][:70]}*" if fresh else "")})
        if len(sources) >= limit:
            say({"type": "thought", "content": f"Source budget for this step reached ({len(sources)}/{max_sources} sources)"})
        return found

    def read_pages(urls, why) -> int:
        urls = list(dict.fromkeys(u for u in urls if u))[:3]
        if not urls:
            return 0
        say({"type": "tool_call", "name": "read_pages",
             "args": {"urls": [re.sub(r"^https?://(www\.)?", "", u).rstrip("/")[:60] for u in urls], "why": why}})
        try:
            res = llm.tavily().extract(urls=urls, extract_depth="basic", timeout=20).get("results", [])
        except Exception as e:
            say({"type": "error", "content": f"page read failed: {e}"})
            return 0
        n = 0
        for page in res:
            text = (page.get("raw_content") or "")[:3500]
            if not text:
                continue
            url = page.get("url") or ""
            for s in sources:
                if s["url"].rstrip("/") == url.rstrip("/"):
                    s.update(content=text, read=True)
                    n += 1
                    break
            else:
                for s in add([{"title": _domain(url), "url": url, "content": text}], why):
                    s["read"] = True
                    n += 1
        stats["pages_read"] += n
        say({"type": "tool_result", "name": "read_pages", "content": f"read {n} of {len(urls)} page(s) in full"})
        return n

    # 1. plan
    say({"type": "thought", "content": f"Planning research on **{company}**"})
    try:
        plan = llm.ask_json(RESEARCH_PLAN, f"COMPANY: {company}")
    except Exception as e:
        say({"type": "error", "content": f"planning failed, using default plan: {e}"})
        plan = {"entity": company, "hypothesis": "", "queries": []}
    if not isinstance(plan, dict):
        plan = {"entity": company, "hypothesis": "", "queries": plan if isinstance(plan, list) else []}
    queries = [q for q in plan.get("queries") or [] if isinstance(q, dict) and q.get("query")][:8]
    if not queries:
        queries = [{"area": a, "query": f"{company} {a.split(',')[0].lower()} risk"} for a in AREAS]
    queries.append({"area": "Overview", "query": f"{company} official website company profile headquarters products"})
    queries.append({"area": "Media & reputation", "query": f"{company} news", "news": True})
    guess = _host(str(plan.get("website") or ""))
    guess = guess if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", guess) else ""
    if guess:
        queries.append({"area": "Company website", "site": guess,
                        "query": f"{company} about company investors sustainability certifications quality"})
    say({"type": "thought", "content": "Research plan: " + "; ".join(f"*{q['area']}*: {q['query']}" for q in queries[:8])
         + (f". Official site is probably **{guess}**" if guess else "")})

    # 2. broad search (snippets only); keep ~40% of the source budget for digging deeper
    search_batch(queries, per_query=4, limit=round(max_sources * 0.6))

    # 3. find and read the company's own site: planner's guess first, token heuristic as fallback
    site = guess if guess and any(_on_site(s["url"], guess) for s in sources) else ""
    if not site:
        hosts = [_host(s["url"]) for s in sources if _looks_own(_host(s["url"]), company)]
        site = max(set(hosts), key=hosts.count) if hosts else guess  # unverified guess: try its homepage anyway
        if guess and site != guess:
            say({"type": "thought", "content": f"Planner's domain {guess} not found in results"
                 + (f"; using **{site}** from the results" if site else "")})
    if site:
        # same brand on other TLDs/subdomains counts too (knorr-bremse.de and knorr-bremse.com)
        family = [s for s in sources if _on_site(s["url"], site) or _label(_host(s["url"])) == _label(site)]
        hosts = [_host(s["url"]) for s in family]
        home = max(set(hosts), key=hosts.count) if hosts else site
        own = [s for s in family if urlparse(s["url"]).path.strip("/")]
        pages = sorted([s for s in own if _SITE_PAGE.search(urlparse(s["url"]).path)], key=lambda s: s["n"])[:2] or own[:1]
        read_pages([f"https://{home}/"] + [s["url"] for s in pages], "company website")
    else:
        say({"type": "thought", "content": "Could not identify the company's own website"})

    # 4. first triage, then dig deeper round by round until the flags are settled
    flags: dict[str, dict] = {}
    gaps: list[dict] = []

    def review(fresh_from: int, first: bool) -> dict:
        state = [{k: f.get(k) for k in ("id", "flag", "severity", "area", "status", "evidence", "sources")}
                 for f in flags.values()]
        note = ("FIRST PASS: no flags yet. Mark every flag needs_more with follow-up queries to confirm, date and size it."
                if first else f"FLAGS SO FAR:\n{json.dumps(state, ensure_ascii=False)}\n\nSources after [{fresh_from}] are "
                f"new this round. QUERIES ALREADY RUN (never repeat or paraphrase them; a flag that stays needs_more "
                f"needs a different angle, e.g. court, regulator, year, amount, local-language press):\n- "
                + "\n- ".join(sorted(ran)))
        try:
            res = _ask_by(REVIEW_TIMEOUT_S, RESEARCH_REVIEW, f"COMPANY: {company}\n{note}\n\nSOURCES:\n"
                          + _digest(sources, fresh_from, fresh_chars=400 if first else 700), retries=1, max_tokens=4000)
        except TimeoutError:
            say({"type": "error", "content": f"review took over {REVIEW_TIMEOUT_S}s, continuing with the evidence so far"})
            return {"_failed": True}
        except Exception as e:
            say({"type": "error", "content": f"review failed: {str(e)[:200]}"})
            return {"_failed": True}
        return res if isinstance(res, dict) else {"flags": res} if isinstance(res, list) else {}

    def merge(res: dict):
        for f in res.get("flags") or []:
            if not isinstance(f, dict) or not f.get("flag"):
                continue
            fid = str(f.get("id") or "").strip().upper()
            if fid not in flags:  # LLM dropped the id: match an existing flag by title
                title = str(f["flag"]).lower()
                fid = next((k for k, g in flags.items() if SequenceMatcher(None, title, str(g.get("flag", "")).lower())
                            .ratio() > 0.75), fid)
            if fid not in flags:
                if len(flags) >= 5:
                    continue
                fid = f"F{len(flags) + 1}"
                flags[fid] = {"id": fid, "found_round": rounds, "checked_rounds": 0}
            raw = re.sub(r"[\s-]+", "_", str(f.get("status") or "").strip().lower())
            status = {"verified": "confirmed", "resolved": "refuted", "false": "refuted"}.get(raw, raw)
            status = status if status in RESOLUTION else "needs_more"
            flags[fid].update({"flag": f.get("flag"), "severity": f.get("severity"), "area": f.get("area", ""),
                               "status": status, "resolution": RESOLUTION[status], "evidence": f.get("evidence", ""),
                               "sources": f.get("sources") or flags[fid].get("sources") or [],
                               "follow_up": [q for q in _as_list(f.get("follow_up")) if isinstance(q, str) and q.strip()][:2]})
        gaps[:] = [g for g in res.get("gaps") or [] if isinstance(g, dict) and g.get("query")][:2]

    def sev(f):
        try:
            return -float(f.get("severity") or 0)
        except (TypeError, ValueError):
            return 0

    rounds, stop = 0, "max rounds reached"
    merge(review(0, first=True))
    if flags:
        say({"type": "thought", "content": "🚩 Red flags to verify: " +
             "; ".join(f"**{f['flag']}** (severity {f['severity']})" for f in sorted(flags.values(), key=sev))})
    else:
        say({"type": "thought", "content": "No red flags in first pass"})

    dig_log = []
    while True:
        if rounds >= max_rounds:
            break
        if time.time() - t0 > time_budget_s:
            stop = f"time budget of {time_budget_s}s used"
            break
        open_flags = sorted([f for f in flags.values() if f["status"] == "needs_more"], key=sev)[:max_flags]
        deep = []
        for f in open_flags:
            qs = [q for q in (_with_company(q, company) for q in f["follow_up"]) if q.lower() not in ran]
            if not qs and not f.get("auto_query"):  # the LLM gave no new angle: one plain news query on the flag
                f["auto_query"] = True
                qs = [_with_company(f"{f['flag']} latest", company)]
            deep += [{"area": f["area"], "query": q, "news": True, "flag": f["id"]} for q in qs[:2]]
        deep += [{"area": g.get("area", ""), "query": _with_company(g["query"], company)} for g in gaps]
        deep = list({q["query"].lower(): q for q in deep if q["query"].lower() not in ran}.values())[:6]
        if not deep:
            stop = ("no new queries for the open flags" if open_flags else
                    "all flags settled" if flags else "no red flags or gaps left to check")
            break
        if len(sources) >= max_sources:
            stop = f"source budget of {max_sources} reached"
            break
        rounds += 1
        targets = [f"**{f['flag']}**" for f in open_flags if any(q.get("flag") == f["id"] for q in deep)]
        gap_areas = [g.get("area", "") for g in gaps]
        say({"type": "thought", "content": f"Round {rounds}: digging into " + ", ".join(
            targets + ([f"gaps in *{', '.join(gap_areas)}*"] if gap_areas else []))})
        before = len(sources)
        # spread the remaining budget over the remaining rounds
        limit = before + -(-(max_sources - before) // (max_rounds - rounds + 1))
        found = search_batch(deep, per_query=4, limit=limit)
        for f in open_flags:
            f["checked_rounds"] += 1
        if len(sources) == before:
            stop = "nothing new found"
            say({"type": "thought", "content": f"Round {rounds} found no new sources, stopping"})
            dig_log.append({"round": rounds, "queries": [q["query"] for q in deep], "new_sources": 0})
            break
        # read the strongest new evidence in full: the top fresh hit of each red-flag query
        top = [res[0]["url"] for q, res in found.items() if res and any(d["query"] == q and d.get("flag") for d in deep)]
        read = read_pages(top or [s["url"] for s in sources[before:before + 3]], "red-flag evidence")
        res = review(before, first=False)
        if res.get("_failed"):
            stop = "review step failed"
            dig_log.append({"round": rounds, "queries": [q["query"] for q in deep], "new_sources": len(sources) - before,
                            "pages_read": read, "review_failed": True})
            break
        merge(res)
        verdicts = {"confirmed": "✅ confirmed", "refuted": "❌ refuted", "needs_more": "🔎 still open"}
        say({"type": "thought", "content": f"Round {rounds} review: " + ("; ".join(
            f"**{f['flag']}** {verdicts[f['status']]}" for f in sorted(flags.values(), key=sev)) or "no flags")
            + (f". {res['reason']}" if res.get("reason") else "")})
        dig_log.append({"round": rounds, "queries": [q["query"] for q in deep], "new_sources": len(sources) - before,
                        "pages_read": read, "flags": {f["id"]: f["resolution"] for f in flags.values()},
                        "done": res.get("done") is True, "reason": res.get("reason", "")})
        if res.get("done") is True:
            stop = "agent judged the picture complete"
            break
    say({"type": "thought", "content": f"Stopped digging after {rounds} round(s): {stop}"})

    # 5. report
    corpus, used = _corpus(sources)
    say({"type": "thought", "content": f"Writing the cited report from {used} sources ({len(corpus) // 1000}k chars)"})
    final = [{k: f.get(k) for k in ("id", "flag", "severity", "area", "resolution", "evidence", "sources")}
             for f in sorted(flags.values(), key=sev)]
    rep = llm.ask_json(RESEARCH_REPORT, f"COMPANY: {company}\nRESEARCH FLAGS: {json.dumps(final, ensure_ascii=False)}"
                       f"\n\nSOURCES:\n{corpus}", max_tokens=6000)
    if not isinstance(rep, dict):
        raise ValueError("report writer returned no JSON object")
    if not rep.get("website") and site:
        rep["website"] = f"https://{site}"
    out = finalize_report(rep, sources, plan, sorted(flags.values(), key=sev), rounds=rounds)
    out.update({"stop_reason": stop, "dig_log": dig_log, "company_site": site, "pages_read": stats["pages_read"],
                "queries_run": stats["queries"], "elapsed_s": round(time.time() - t0)})
    return out


@lru_cache
def _quantiles() -> tuple[dict, dict]:
    q = ds.df()[ds.SCORES].quantile([0.1, 0.9])
    return q.loc[0.1].to_dict(), q.loc[0.9].to_dict()


_MULTI_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)+)\]")
_CITE = re.compile(r"\[(\d+)\]")


def _clean_text(text, valid: set, dropped: list) -> str:
    """Normalise [1, 2] to [1][2] and drop citation numbers that are not in the source list."""
    if not isinstance(text, str):
        return text
    text = _MULTI_CITE.sub(lambda m: "".join(f"[{x.strip()}]" for x in m.group(1).split(",")), text)

    def keep(m):
        if int(m.group(1)) in valid:
            return m.group(0)
        dropped.append(int(m.group(1)))
        return ""
    return _CITE.sub(keep, text)


def _clean_ns(ns, valid: set, dropped: list) -> list[int]:
    out = []
    for n in ns if isinstance(ns, list) else []:
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        (out if n in valid else dropped).append(n)
    return list(dict.fromkeys(out))


def finalize_report(rep: dict, sources: list[dict], plan: dict, flags: list, rounds: int | None = None) -> dict:
    """Turn the LLM report into a dataset-comparable risk profile with an index computed by the dataset's own formula."""
    valid = {s["n"] for s in sources}
    dropped: list[int] = []
    scores = rep.get("scores") or {}
    for d in scores.values():
        if isinstance(d, dict):
            d["sources"] = _clean_ns(d.get("sources"), valid, dropped)
            d["evidence"] = _clean_text(d.get("evidence", ""), valid, dropped)
    by_id = {f.get("id"): f for f in flags if isinstance(f, dict)}
    for f in flags:
        if isinstance(f, dict) and "sources" in f:
            f["sources"] = _clean_ns(_as_list(f.get("sources")), valid, [])
    status_res = {"confirmed": "confirmed", "resolved": "confirmed", "unconfirmed": "unresolved"}
    for f in rep.get("red_flags") or []:
        if isinstance(f, dict):
            f["sources"] = _clean_ns(f.get("sources"), valid, dropped)
            f["detail"] = _clean_text(f.get("detail", ""), valid, dropped)
            linked = by_id.get(str(f.get("flag_id") or "").strip().upper())
            f["resolution"] = (linked or {}).get("resolution") or status_res.get(f.get("status"), "unresolved")
    for k in ("overview", "recommendation"):
        rep[k] = _clean_text(rep.get(k, ""), valid, dropped)
    rep["strengths"] = [_clean_text(s, valid, dropped) for s in rep.get("strengths") or []]

    mu = ds.means()
    lo_q, hi_q = _quantiles()
    filled, low, high, known_w, unknown = {}, {}, {}, 0.0, []
    for c, w in ds.TRI_WEIGHTS.items():
        v = (scores.get(c) or {}).get("score") if isinstance(scores.get(c), dict) else None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            filled[c] = low[c] = high[c] = max(0.0, min(100.0, float(v)))
            known_w += w
        else:
            filled[c] = float(mu[c])  # no evidence: assume dataset average, shown as unknown
            low[c], high[c] = float(lo_q[c]), float(hi_q[c])  # plausible range: dataset P10..P90
            unknown.append(c)
    tri = round(sum(filled[c] * w for c, w in ds.TRI_WEIGHTS.items()))
    tri_low = round(sum(low[c] * w for c, w in ds.TRI_WEIGHTS.items()))
    tri_high = round(sum(high[c] * w for c, w in ds.TRI_WEIGHTS.items()))
    rep.update({"total_risk_index": tri, "level": ds.level(tri), "evidence_coverage": round(known_w, 2),
                "riskier_than_pct": ds.riskier_than("Total_Risk_Index", tri), "filled_scores": filled,
                "tri_low": tri_low, "tri_high": tri_high, "unknown_dimensions": unknown,
                "rounds": rounds if rounds is not None else rep.get("rounds", 0),
                "dropped_citations": sorted(set(dropped)),
                "sources": [{"n": s["n"], "title": s["title"], "url": s["url"], "area": s.get("area", ""),
                             "date": s.get("date", ""), "read": bool(s.get("read"))} for s in sources],
                "plan": plan, "triage_flags": flags, "researched_at": time.strftime("%Y-%m-%d %H:%M")})
    return rep


def report_markdown(rep: dict) -> str:
    src = {s["n"]: s for s in rep.get("sources", [])}

    def cite(ns):
        return " ".join(f"[[{n}]]({src[n]['url']})" for n in ns or [] if n in src)

    rng = (f" Range **{rep['tri_low']}–{rep['tri_high']}** if the unknown dimensions sit anywhere between the "
           f"dataset's 10th and 90th percentile." if "tri_low" in rep else "")
    depth = f" · {rep['rounds']} dig-deeper round(s)" if "rounds" in rep else ""
    lines = [f"# Supplier risk report: {rep.get('company', '')}", "",
             f"*Researched {rep.get('researched_at', '')} · {len(src)} sources{depth} · verdict: **{rep.get('verdict', '')}***", "",
             rep.get("overview", ""), "",
             f"**Total Risk Index (dataset formula): {rep['total_risk_index']} ({rep['level']})**, riskier than "
             f"{rep['riskier_than_pct']:.0f}% of the 10,000 suppliers in the dataset. Evidence covers "
             f"{rep['evidence_coverage']:.0%} of the index weight; dimensions without evidence are set to the dataset average."
             + rng, "",
             "## Recommendation", rep.get("recommendation", ""), "", "## Red flags"]
    for f in rep.get("red_flags", []) or ["none found"]:
        if isinstance(f, dict):
            res = f" · {f['resolution']}" if f.get("resolution") else ""
            lines.append(f"- **{f.get('title')}** (severity {f.get('severity')}/5, {f.get('status', '')}{res}): "
                         f"{f.get('detail', '')} {cite(f.get('sources'))}")
        else:
            lines.append(f"- {f}")
    refuted = [f for f in rep.get("triage_flags") or [] if isinstance(f, dict) and f.get("resolution") == "refuted"]
    if refuted:
        lines += ["", "## Checked and refuted"] + [f"- **{f.get('flag')}**: {f.get('evidence', '')} {cite(f.get('sources'))}"
                                                    for f in refuted]
    lines += ["", "## Strengths"] + [f"- {s}" for s in rep.get("strengths", [])]
    lines += ["", "## Risk dimensions", "", "| Dimension | Score | Evidence |", "|---|---|---|"]
    for c in ds.SCORES:
        d = (rep.get("scores") or {}).get(c) or {}
        sc = d.get("score")
        lines.append(f"| {ds.label(c)} | {sc if sc is not None else 'no evidence'} | {d.get('evidence', '')} {cite(d.get('sources'))} |")
    lines += ["", "## Sources"] + [f"{s['n']}. [{s['title']}]({s['url']})" for s in rep.get("sources", [])]
    return "\n".join(lines)
