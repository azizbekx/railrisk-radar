"""Sourcing agent: the buyer names a component, agents narrow 10,000 suppliers down to a recommended three.

  1. Screen (Python): who makes the component, passes the part type's risk gate and holds the required
     certifications. The lowest-risk 50 become the longlist and are sent a request for quotation (RFQ).
  2. Offers (offer analyst agent): every offer gets a score from price, quality, delivery reliability, lead time
     and risk; the agent picks 7 finalists from the best 12 and says why.
  3. Deep check: the four risk specialists of core/team.py and a market agent reading live news work in parallel;
     the leader agent then picks the final three.

The dataset is anonymized and has no product catalog or prices, so what each supplier makes, its certifications and
its offer are SIMULATED: deterministic per supplier and component, so the same request always gets the same offers.
Python computes every number; the agents choose, judge and explain.

    .venv/bin/python -m core.sourcing brake_control_unit 400 30"""
import hashlib
import json
import re
import sys
import time
from functools import lru_cache

from core import dataset as ds, llm, team
from core.fmt import eur
from core.llm import ContextPool as ThreadPoolExecutor  # workers keep the session's model choice

LONGLIST, CANDIDATES, FINALISTS, TOP = 50, 12, 7, 3
AGENT_TIMEOUT_S = 150  # a stalled agent call is abandoned; the run continues with the Python ranking

# Rail components the buyer can source. unit_eur and lead_weeks are typical market values that the simulated offers
# scatter around; share is the fraction of the 10,000 suppliers that make the component; market feeds the news search.
COMPONENTS = {
    "brake_control_unit": {"label": "Brake control unit", "part_type": "safety_critical", "unit_eur": 18500, "lead_weeks": 22,
                           "share": 0.07, "certs": ["ISO/TS 22163 (IRIS)", "EN 50155", "EN 45545-2"],
                           "aliases": ["brake", "brakes", "braking", "bcu"], "market": "railway brake systems"},
    "bogie_frame": {"label": "Bogie frame", "part_type": "safety_critical", "unit_eur": 48000, "lead_weeks": 26,
                    "share": 0.07, "certs": ["ISO/TS 22163 (IRIS)", "EN 15085-2"],
                    "aliases": ["bogie", "bogies", "frame"], "market": "rail bogie steel castings"},
    "wheelset": {"label": "Wheelset", "part_type": "safety_critical", "unit_eur": 14000, "lead_weeks": 24,
                 "share": 0.07, "certs": ["ISO/TS 22163 (IRIS)", "EN 13260"],
                 "aliases": ["wheel", "wheels", "axle", "axles"], "market": "railway wheels and axles"},
    "coupler": {"label": "Automatic coupler", "part_type": "safety_critical", "unit_eur": 23000, "lead_weeks": 20,
                "share": 0.07, "certs": ["ISO/TS 22163 (IRIS)", "EN 16019"],
                "aliases": ["coupler", "couplers", "coupling"], "market": "railway couplers"},
    "door_system": {"label": "Passenger door system", "part_type": "safety_critical", "unit_eur": 9800, "lead_weeks": 16,
                    "share": 0.07, "certs": ["ISO/TS 22163 (IRIS)", "EN 14752"],
                    "aliases": ["door", "doors", "entrance"], "market": "train door systems"},
    "traction_converter": {"label": "Traction converter", "part_type": "safety_critical", "unit_eur": 145000, "lead_weeks": 32,
                           "share": 0.07, "certs": ["ISO/TS 22163 (IRIS)", "EN 50155", "EN 61287-1"],
                           "aliases": ["traction", "converter", "inverter", "propulsion"], "market": "rail traction converters power semiconductors"},
    "hvac_unit": {"label": "HVAC unit", "part_type": "standard", "unit_eur": 29000, "lead_weeks": 18,
                  "share": 0.07, "certs": ["ISO 9001", "EN 14750", "EN 45545-2"],
                  "aliases": ["hvac", "air conditioning", "climate", "heating"], "market": "rail HVAC units"},
    "passenger_seat": {"label": "Passenger seat", "part_type": "standard", "unit_eur": 1150, "lead_weeks": 12,
                       "share": 0.07, "certs": ["ISO 9001", "EN 45545-2"],
                       "aliases": ["seat", "seats", "seating"], "market": "rail passenger seating"},
    "led_lighting": {"label": "Interior LED lighting", "part_type": "standard", "unit_eur": 460, "lead_weeks": 8,
                     "share": 0.07, "certs": ["ISO 9001", "EN 45545-2", "EN 13272"],
                     "aliases": ["lighting", "light", "lights", "led", "lamp"], "market": "LED lighting rail"},
    "cable_harness": {"label": "Cable harness", "part_type": "standard", "unit_eur": 1850, "lead_weeks": 10,
                      "share": 0.07, "certs": ["ISO 9001", "EN 45545-2"],
                      "aliases": ["cable", "cables", "harness", "wiring"], "market": "copper wire harness"},
    "passenger_info_display": {"label": "Passenger information display", "part_type": "standard", "unit_eur": 3300,
                               "lead_weeks": 12, "share": 0.07, "certs": ["ISO 9001", "EN 50155"],
                               "aliases": ["display", "displays", "screen", "passenger information", "pis"],
                               "market": "rail passenger information systems displays chips"},
    "seat_cover": {"label": "Seat covers", "part_type": "budget", "unit_eur": 85, "lead_weeks": 6,
                   "share": 0.07, "certs": ["EN 45545-2"],
                   "aliases": ["seat cover", "seat covers", "upholstery", "fabric"], "market": "upholstery fabric textiles"},
    "signage": {"label": "Signage and labels", "part_type": "budget", "unit_eur": 38, "lead_weeks": 4,
                "share": 0.07, "certs": [], "aliases": ["sign", "signs", "signage", "label", "labels", "sticker"],
                "market": "signage printing"},
    "fasteners": {"label": "Fasteners and brackets", "part_type": "budget", "unit_eur": 2.4, "lead_weeks": 4,
                  "share": 0.07, "certs": ["ISO 9001"], "aliases": ["fastener", "fasteners", "bolt", "bolts", "screw", "screws", "bracket", "brackets"],
                  "market": "industrial fasteners steel"},
}

# How the offer score splits the non-price share. Price's share comes from the part type (dataset.PART_TYPES).
REST = {"risk": 0.4, "quality": 0.3, "delivery": 0.2, "lead_time": 0.1}


def weights(part_type: str) -> dict:
    pw = float(ds.PART_TYPES[part_type]["price_weight"])
    return {"price": pw, **{k: round((1 - pw) * v, 3) for k, v in REST.items()}}


def _u(*parts) -> float:
    """Deterministic uniform number in [0, 1) from the given parts."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def _sig(x: float) -> float:
    """Round a price to 3 significant figures, like a quote would be."""
    return float(f"{x:.3g}")


# ---------- 1. screen ----------

@lru_cache(maxsize=32)
def makers(component: str) -> tuple[str, ...]:
    share = COMPONENTS[component]["share"]
    return tuple(i for i in ds.df().index if _u(i, component, "makes") < share)


def certs_held(sid: str, component: str) -> dict[str, bool]:
    """Each required certificate is held with a probability that falls with compliance and quality risk."""
    r = ds.df().loc[sid]
    p = 0.98 - 0.3 * r["Compliance_Risk_Score"] / 100 - 0.1 * r["Quality_Risk_Score"] / 100
    return {c: _u(sid, component, c) < p for c in COMPONENTS[component]["certs"]}


def screen(component: str, risk_weights: dict) -> tuple[list[str], list[dict], dict]:
    """Longlist (the LONGLIST lowest-risk qualified makers), funnel counts, and the risk index per maker."""
    part = COMPONENTS[component]["part_type"]
    d = ds.df()
    mk = list(makers(component))
    gate = ds.part_gate(d.loc[mk], part)
    passed = [i for i in mk if gate[i]]
    certified = [i for i in passed if all(certs_held(i, component).values())]
    risk = ds.lens_index(d.loc[certified], risk_weights).round(1).to_dict() if certified else {}
    longlist = sorted(certified, key=lambda i: (risk[i], i))[:LONGLIST]
    funnel = [
        {"stage": "all", "label": "Suppliers in the dataset", "count": len(d)},
        {"stage": "makers", "label": f"Make {COMPONENTS[component]['label'].lower()}", "count": len(mk)},
        {"stage": "gate", "label": f"Pass the {ds.PART_TYPES[part]['label'].lower()} risk gate", "count": len(passed)},
        {"stage": "certified", "label": "Hold every required certificate", "count": len(certified)},
        {"stage": "longlist", "label": "Lowest risk: sent an RFQ", "count": len(longlist)},
    ]
    return longlist, funnel, risk


# ---------- 2. offers ----------

def offer(sid: str, component: str) -> dict:
    """Simulated RFQ answer. Lower-risk suppliers quote a little higher; weak operations mean longer lead times."""
    spec, r = COMPONENTS[component], ds.df().loc[sid]
    tri = float(r["Total_Risk_Index"])
    price = spec["unit_eur"] * (1 + 0.36 * (_u(sid, component, "price") - 0.5) + 0.12 * (50 - tri) / 50)
    lead = spec["lead_weeks"] * (0.7 + 0.6 * _u(sid, component, "lead")) * (1 + 0.25 * (r["Operational_Resilience_Score"] - 50) / 50)
    warranty = 2 + int(_u(sid, component, "warranty") * 3) + (1 if r["Quality_Risk_Score"] < 35 else 0)
    return {"unit_price": _sig(price), "lead_weeks": max(1, round(lead)), "warranty_years": warranty}


def _pts(vals: dict, invert: bool = False) -> dict:
    """0 = best, 100 = worst within the given suppliers."""
    lo, hi = min(vals.values()), max(vals.values())
    if hi <= lo:
        return {k: 0.0 for k in vals}
    return {k: round(((hi - v) if invert else (v - lo)) / (hi - lo) * 100, 1) for k, v in vals.items()}


def score_offers(ids: list[str], component: str, risk: dict, brief: dict) -> list[dict]:
    """Offer rows ranked by score (0-100, lower = better). Offers that miss the need-by date rank after the rest."""
    d = ds.df()
    w = weights(COMPONENTS[component]["part_type"])
    offers = {i: offer(i, component) for i in ids}
    reliab = {i: round(0.6 * float(d.at[i, "Supplier Delivery Rating"]) + 0.4 * float(d.at[i, "Order Confirmation Rate"]), 1)
              for i in ids}
    pts = {"price": _pts({i: o["unit_price"] for i, o in offers.items()}),
           "quality": _pts({i: float(d.at[i, "Quality_Risk_Score"]) for i in ids}),
           "delivery": _pts(reliab, invert=True),
           "lead_time": _pts({i: o["lead_weeks"] for i, o in offers.items()}),
           "risk": _pts({i: risk[i] for i in ids})}
    need, target, qty = brief.get("need_by_weeks"), brief.get("target_unit_price"), brief["quantity"]
    rows = []
    for i in ids:
        r, o = d.loc[i], offers[i]
        rows.append({
            "id": i, "name": r["Supplier Name"], **o, "total": round(o["unit_price"] * qty, 2),
            "late": bool(need and o["lead_weeks"] > need), "over_budget": bool(target and o["unit_price"] > target),
            "certs": list(certs_held(i, component)),
            "tri": int(r["Total_Risk_Index"]), "level": r["Total_Risk_Index_Level"], "risk_index": risk[i],
            "quality_risk": int(r["Quality_Risk_Score"]), "delivery": float(r["Supplier Delivery Rating"]),
            "confirmation": float(r["Order Confirmation Rate"]), "change_rate": float(r["Order Change Rate"]),
            "reliability": reliab[i], "sourcing": r["Sourcing Risk Level"], "complexity": r["Supply Chain Complexity"],
            "pts": {k: pts[k][i] for k in pts},
            "score": round(sum(w[k] * pts[k][i] for k in w), 1),
        })
    rows.sort(key=lambda x: (x["late"], x["score"], x["risk_index"], x["id"]))
    for n, x in enumerate(rows, start=1):
        x["rank"] = n
    return rows


def _money(x: float) -> str:
    """Exact unit price (core.fmt.eur rounds to €k, which hides the differences between quotes)."""
    return f"€{x:,.0f}" if x >= 100 else f"€{x:.2f}"


def _offer_fact(x: dict) -> dict:
    return {"id": x["id"], "rank": x["rank"], "offer_score": x["score"], "unit_price": _money(x["unit_price"]), "total": eur(x["total"]), "lead_weeks": x["lead_weeks"], "late": x["late"],
            "over_budget": x["over_budget"], "warranty_years": x["warranty_years"], "risk_index": x["risk_index"],
            "TRI": x["tri"], "quality_risk": x["quality_risk"], "delivery_rating_pct": x["delivery"],
            "confirmation_rate_pct": x["confirmation"], "order_change_rate_pct": x["change_rate"],
            "sourcing_risk": x["sourcing"], "points_0_best_100_worst": x["pts"]}


# ---------- prompts ----------

INTAKE = """You turn a rail procurement buyer's request into a sourcing brief. Pick the component from this catalog
(key: label): {catalog}
Return JSON only: {{"component": "catalog key or empty if none fits", "quantity": integer or null,
"need_by_weeks": integer weeks from today or null (convert months x 4.3), "target_unit_price": EUR number or null,
"notes": "anything else that matters for the choice, one sentence, or empty"}}"""

ANALYST = f"""You are the offer analyst in a sourcing team for Siemens rail procurement. Suppliers that make the
component, pass the risk gate and hold the certificates were sent an RFQ. You get the brief, the scoring weights and
the best {CANDIDATES} offers ranked by offer score (0-100, lower = better; points per dimension: 0 = best of the
longlist, 100 = worst). Choose exactly {FINALISTS} finalists for a deep risk check. Follow the ranking unless an offer
has a concrete problem (late delivery, over budget, a weak delivery or quality record for this kind of part, a price
far below the others that suggests a capability gap). Risk and quality scores: higher = riskier. Quote numbers.
Return JSON only:
{{"finalists": ["{FINALISTS} supplier IDs"], "reasons": {{"<ID>": "why it goes through, with numbers"}},
 "passed_over": [{{"id": "ID from the {CANDIDATES} not chosen", "reason": "short, with a number"}}],
 "summary": "two sentences on what the offers look like"}}"""

MARKET = """You are the market intelligence agent in a sourcing team for Siemens rail procurement. You get the
component being bought and recent news results. Find what in the market matters for choosing a supplier now:
shortages, raw material and energy prices, lead times, capacity, insolvencies, strikes, regulation, tariffs.
Skip general news with no link to rail, this component, its materials or its logistics.
Use only the numbered results. Return JSON only:
{"summary": "one or two sentences on the market right now",
 "signals": [{"title": "short", "source": result number, "date": "YYYY-MM-DD or empty", "severity": 1-5,
              "impact": "what it means for this purchase", "areas": ["Financial|Operations & Quality|Compliance & ESG|Geopolitics & Reputation"]}],
 "advice": "what kind of supplier this market favours, one sentence (e.g. strong finances, short lead times)"}
Up to 5 signals, most relevant first. An empty list is fine if nothing relevant."""

LEADER = f"""You lead a sourcing team for Siemens rail procurement and pick the final {TOP} suppliers to recommend
from {FINALISTS} finalists. You get the brief, each finalist's offer and final score (half offer score, half the
team's risk score; both 0-100, lower = better, computed exactly), the four risk specialists' reports and the market
agent's live news signals. Follow the final score unless a red flag or a market signal is a stated reason to change
the order. Quote only numbers from the input. Risk scores: higher = riskier.
Return JSON only:
{{"top": [{{"id": "ID", "role": "2-4 words, e.g. Best overall / Best price / Lowest risk",
          "why": "two sentences with numbers", "pros": ["2-3 short"], "cons": ["1-2 short"],
          "watch": "one concrete contract or monitoring measure"}}],
 "not_chosen": [{{"id": "ID", "reason": "short, with a number"}}],
 "summary": "two sentences for the buyer's manager"}}
"top" has exactly {TOP} entries, best first; "not_chosen" covers the other finalists."""


def _ask(system: str, user: str, max_tokens: int = 5000) -> tuple[dict, str]:
    """team._ask_json with a wall-clock limit (raises TimeoutError); a stalled call finishes in the background."""
    ex = ThreadPoolExecutor(1)
    fut = ex.submit(team._ask_json, system, user, max_tokens)
    ex.shutdown(wait=False)
    return fut.result(timeout=AGENT_TIMEOUT_S)


def _ids(raw, allowed: list[str]) -> list[str]:
    out = []
    for x in raw if isinstance(raw, list) else [raw]:
        sid = ds.resolve(x if isinstance(x, str) else (x or {}).get("id") if isinstance(x, dict) else None)
        if sid in allowed and sid not in out:
            out.append(sid)
    return out


# ---------- intake ----------

NUM = r"(\d[\d,.]*)\s*(k)?"


def _fallback_parse(text: str) -> dict:
    t = text.lower()
    comp = ""
    for key, spec in COMPONENTS.items():  # longest alias wins, so "seat covers" beats "seat"
        for a in sorted(spec["aliases"] + [spec["label"].lower()], key=len, reverse=True):
            if re.search(rf"\b{re.escape(a)}\b", t) and (not comp or len(a) > comp[1]):
                comp = (key, len(a))
    weeks = re.search(r"(\d+)\s*(weeks?|months?)", t)
    price = re.search(r"(?:€|eur\s*)" + NUM + r"|" + NUM + r"\s*(?:€|eur)", t)
    p = None
    if price:
        g = price.groups()
        p = float((g[0] or g[2]).replace(",", "")) * (1000 if (g[1] or g[3]) else 1)
    used = [m.span() for m in (weeks, price) if m]
    # quantity: the first number that is not the deadline or the price
    qty = next((m for m in re.finditer(r"\d[\d,]*", t) if not any(a <= m.start() < b for a, b in used)), None)
    return {"component": comp[0] if comp else "", "quantity": int(qty.group().replace(",", "")) if qty else None,
            "need_by_weeks": (int(weeks.group(1)) if weeks.group(2).startswith("week") else round(int(weeks.group(1)) * 4.3)) if weeks else None,
            "target_unit_price": p, "notes": ""}


def parse_request(text: str) -> dict:
    """Plain-language request -> brief fields. Uses the LLM, falls back to keyword matching."""
    base = _fallback_parse(text)
    try:
        catalog = "; ".join(f"{k}: {v['label']}" for k, v in COMPONENTS.items())
        data, _ = _ask(INTAKE.format(catalog=catalog), text, 1500)
    except Exception:
        return {**base, "parsed_by": "keywords"}
    out = {"component": data.get("component") if data.get("component") in COMPONENTS else base["component"],
           "parsed_by": "agent"}
    for k, cast in (("quantity", int), ("need_by_weeks", int), ("target_unit_price", float)):
        try:
            v = cast(float(data[k])) if data.get(k) not in (None, "") else base[k]
            out[k] = v if v is None or v > 0 else base[k]
        except (TypeError, ValueError):
            out[k] = base[k]
    out["notes"] = str(data.get("notes") or "")[:300]
    return out


# ---------- the run ----------

def _severity(v) -> int:
    try:
        return max(1, min(5, round(float(v))))
    except (TypeError, ValueError):
        return 2


def _market(component: str, say) -> dict:
    spec = COMPONENTS[component]
    queries = [f"{spec['market']} supply shortage prices 2026", f"railway {spec['label'].lower()} supplier news"]
    results, seen = [], set()
    for q in queries:
        say({"agent": "Market", "type": "tool_call", "name": "search_news", "args": {"query": q}})
        try:
            for r in llm.search_news(q, days=120, max_results=5):
                if r["url"] and r["url"] not in seen:
                    seen.add(r["url"])
                    results.append(r)
        except Exception as e:
            say({"agent": "Market", "type": "error", "content": f"search failed: {e}"})
            break
    if not results:
        say({"agent": "Market", "type": "done", "content": "No live news available, so the team decides on the dataset alone"})
        return {"summary": "", "signals": [], "advice": "", "sources": [], "error": "no news results"}
    say({"agent": "Market", "type": "tool_result", "name": "search_news", "content": f"{len(results)} recent articles"})
    news = "\n\n".join(f"[{n}] {r['title']} ({r['date']})\n{r['content']}" for n, r in enumerate(results, start=1))
    try:
        data, reasoning = _ask(MARKET, f"COMPONENT: {spec['label']} for rolling stock\n\nNEWS:\n{news}", 3000)
    except Exception as e:
        say({"agent": "Market", "type": "error", "content": f"agent failed: {e}"})
        return {"summary": "", "signals": [], "advice": "", "sources": results, "error": str(e)}
    signals = []
    for s in data.get("signals") or []:
        if not isinstance(s, dict):
            continue
        try:
            n = int(s.get("source"))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= len(results):
            r = results[n - 1]
            signals.append({"title": str(s.get("title") or r["title"]), "url": r["url"], "date": s.get("date") or r["date"] or "",
                            "severity": _severity(s.get("severity")),
                            "impact": str(s.get("impact") or ""), "areas": [a for a in s.get("areas") or [] if a in team.AGENTS]})
    out = {"summary": str(data.get("summary") or ""), "signals": signals[:5], "advice": str(data.get("advice") or ""),
           "sources": results, "reasoning": reasoning}
    say({"agent": "Market", "type": "done", "content": f"{len(out['signals'])} market signal(s). {out['summary']}"})
    return out


def _specialist(area: str, ids: list[str], idx: dict, ctx: str, weight: float, say) -> dict:
    t0 = time.time()
    say({"agent": area, "type": "status", "content": f"Checking {len(ids)} finalists on {len(team.AGENTS[area]['columns'])} metrics"})
    try:
        rep, reasoning = _ask(team.specialist_prompt(area), json.dumps(
            {"buying_context": ctx, "weight_in_decision": weight, **team.area_facts(area, ids, idx)}, default=str))
    except Exception as e:
        rep, reasoning = {"verdict": f"Agent failed: {e}", "error": str(e)}, ""
    best = ds.resolve(rep.get("best"))
    rep["best"] = best if best in ids else min(ids, key=idx[area].get)
    flags = [f for f in rep.get("red_flags") or [] if isinstance(f, dict) and ds.resolve(f.get("supplier")) in ids]
    for f in flags:
        f["supplier"] = ds.resolve(f["supplier"])
    rep.update({"red_flags": flags, "reasoning": reasoning, "seconds": round(time.time() - t0, 1)})
    rep.pop("chart", None)
    say({"agent": area, "type": "error" if "error" in rep else "done", "content": f"Picks **{rep['best']}**. {rep.get('verdict', '')}"})
    return rep


def brief_of(component: str, quantity: int | None, need_by_weeks: int | None, target_unit_price: float | None, notes: str) -> dict:
    spec = COMPONENTS[component]
    part = spec["part_type"]
    return {"component": component, "label": spec["label"], "part_type": part, "part_label": ds.PART_TYPES[part]["label"],
            "certs": spec["certs"], "quantity": max(1, int(quantity or 1)),
            "need_by_weeks": int(need_by_weeks) if need_by_weeks else None,
            "target_unit_price": float(target_unit_price) if target_unit_price else None, "notes": (notes or "").strip()}


def _kind(b: dict) -> str:
    """'Safety-critical part', 'Standard part', 'Non-critical / budget part'."""
    return b["part_label"] if b["part_label"].endswith("part") else f"{b['part_label']} part"


def _context(b: dict) -> str:
    bits = [f"Buying {b['quantity']:,} x {b['label']} ({_kind(b).lower()}) for rolling stock"]
    if b["need_by_weeks"]:
        bits.append(f"needed within {b['need_by_weeks']} weeks")
    if b["target_unit_price"]:
        bits.append(f"target price {eur(b['target_unit_price'])} per unit")
    return ", ".join(bits) + "." + (f" Buyer notes: {b['notes']}" if b["notes"] else "")


def run(component: str, quantity: int | None = None, need_by_weeks: int | None = None, target_unit_price: float | None = None,
        notes: str = "", lens_name: str | None = None, lens_weights: dict | None = None, log=None) -> dict:
    say = log or (lambda _: None)
    if component not in COMPONENTS:
        raise ValueError(f"Unknown component: {component}")
    b = brief_of(component, quantity, need_by_weeks, target_unit_price, notes)
    part = b["part_type"]
    lens_name = lens_name or ds.PART_TYPES[part]["lens"]
    risk_w = ds.normalize_weights(lens_weights or ds.LENSES.get(lens_name) or ds.TRI_WEIGHTS)
    ctx = _context(b)
    t_start = time.time()

    # 1. screen
    say({"agent": "Sourcing", "type": "thought", "content": f"{ctx} Screening {len(ds.df()):,} suppliers"})
    longlist, funnel, risk = screen(component, risk_w)
    for f in funnel[1:]:
        say({"agent": "Sourcing", "type": "tool_result", "name": f["stage"], "content": f"{f['label']}: {f['count']:,}"})
    if len(longlist) < TOP:
        raise ValueError(f"Only {len(longlist)} qualified supplier(s) make {b['label'].lower()}; widen the request")
    say({"agent": "Sourcing", "type": "done", "content": f"RFQ sent to the **{len(longlist)}** lowest-risk qualified makers"})

    # market news does not depend on the offers, so it runs while the offers are judged
    pool = ThreadPoolExecutor(5)
    market_f = pool.submit(_market, component, say)

    # 2. offers -> finalists
    rows = score_offers(longlist, component, risk, b)
    w = weights(part)
    cands = rows[:CANDIDATES]
    late = sum(r["late"] for r in rows)
    say({"agent": "Offer analyst", "type": "thought", "content": f"{len(rows)} offers scored: price {w['price']:.0%}, risk "
         f"{w['risk']:.0%}, quality {w['quality']:.0%}, delivery {w['delivery']:.0%}, lead time {w['lead_time']:.0%}"
         + (f". {late} miss the need-by date" if late else "") + f". Reviewing the best {len(cands)}"})
    cand_ids = [c["id"] for c in cands]
    try:
        an, an_reasoning = _ask(ANALYST, json.dumps({"brief": ctx, "weights": w, "candidates": [_offer_fact(c) for c in cands]}, default=str))
    except Exception as e:
        say({"agent": "Offer analyst", "type": "error", "content": f"agent failed, keeping the score order: {e}"})
        an, an_reasoning = {}, ""
    finalists = _ids(an.get("finalists"), cand_ids)[:FINALISTS]
    finalists += [i for i in cand_ids if i not in finalists][:FINALISTS - len(finalists)]
    reasons = {ds.resolve(k): str(v) for k, v in (an.get("reasons") or {}).items() if ds.resolve(k) in finalists} \
        if isinstance(an.get("reasons"), dict) else {}
    passed_over = [{"id": ds.resolve(p.get("id")), "reason": str(p.get("reason") or "")} for p in an.get("passed_over") or []
                   if isinstance(p, dict) and ds.resolve(p.get("id")) in cand_ids and ds.resolve(p.get("id")) not in finalists]
    swapped = [i for i in finalists if i not in cand_ids[:FINALISTS]]
    say({"agent": "Offer analyst", "type": "done", "content": f"**{len(finalists)} finalists**: {', '.join(finalists)}"
         + (f". Moved up {', '.join(swapped)} over the score order" if swapped else "")})

    # 3. deep check: four specialists in parallel (market is already running)
    area_w = team.lens_area_weights(risk_w)
    idx = team.area_index(finalists)
    futs = {a: pool.submit(_specialist, a, finalists, idx, ctx, area_w[a], say) for a in team.AGENTS}
    reports = {a: f.result() for a, f in futs.items()}
    market = market_f.result()
    pool.shutdown(wait=False)

    by_id = {r["id"]: r for r in rows}
    team_score = {i: round(sum(area_w[a] * idx[a][i] for a in team.AGENTS), 1) for i in finalists}
    final = {i: round(0.5 * by_id[i]["score"] + 0.5 * team_score[i], 1) for i in finalists}
    order = sorted(finalists, key=lambda i: (final[i], by_id[i]["rank"]))
    say({"agent": "Leader", "type": "thought", "content": f"Weighing 4 risk reports and {len(market['signals'])} market signal(s). "
         f"Best final score: **{order[0]}** ({final[order[0]]})"})
    lead_in = {
        "brief": ctx, "offer_weights": w, "area_weights": area_w,
        "finalists": [{**_offer_fact(by_id[i]), "team_risk_score": team_score[i], "final_score": final[i],
                       "area_risk_index": {a: idx[a][i] for a in team.AGENTS}, "analyst_note": reasons.get(i, "")} for i in order],
        "specialist_reports": {a: {k: r.get(k) for k in ("best", "worst", "verdict", "findings", "red_flags", "confidence")}
                               for a, r in reports.items()},
        "market": {k: market.get(k) for k in ("summary", "signals", "advice")},
    }
    try:
        ld, ld_reasoning = _ask(LEADER, json.dumps(lead_in, default=str), 6000)
    except Exception as e:
        say({"agent": "Leader", "type": "error", "content": f"leader failed, using the final score order: {e}"})
        ld, ld_reasoning = {}, ""
    top_raw = {ds.resolve(t.get("id")): t for t in ld.get("top") or [] if isinstance(t, dict)}
    top_ids = _ids(ld.get("top"), finalists)[:TOP]
    top_ids += [i for i in order if i not in top_ids][:TOP - len(top_ids)]
    flags = {i: [{"area": a, "issue": f.get("issue", "")} for a, r in reports.items() for f in r["red_flags"] if f["supplier"] == i]
             for i in finalists}
    top = []
    for n, i in enumerate(top_ids, start=1):
        t = top_raw.get(i, {})
        ex = ds.explain(i)
        top.append({"id": i, "rank": n, "role": str(t.get("role") or ("Best final score" if i == order[0] else "Runner-up")),
                    "why": str(t.get("why") or reasons.get(i, "")), "pros": [str(p) for p in t.get("pros") or []][:3],
                    "cons": [str(c) for c in t.get("cons") or []][:2], "watch": str(t.get("watch") or ""),
                    "final_score": final[i], "team_score": team_score[i], "area_index": {a: idx[a][i] for a in team.AGENTS},
                    "red_flags": flags[i], "specialist_picks": [a for a, r in reports.items() if r["best"] == i],
                    "drivers": [{"label": p["label"], "value": p["value"], "level": p["level"]} for p in ex["drivers_up"][:3]],
                    "strengths": [{"label": p["label"], "value": p["value"], "level": p["level"]} for p in ex["drivers_down"][:3]]})
    nc_raw = {ds.resolve(x.get("id")): str(x.get("reason") or "") for x in ld.get("not_chosen") or [] if isinstance(x, dict)}
    not_chosen = [{"id": i, "reason": nc_raw.get(i) or f"final score {final[i]}", "final_score": final[i]}
                  for i in order if i not in top_ids]
    say({"agent": "Leader", "type": "done", "content": "Recommends " + ", ".join(f"**{t['id']}**" for t in top)})

    res = {"brief": b, "context": ctx, "lens": lens_name, "weights": w, "funnel": funnel + [
               {"stage": "finalists", "label": "Best offers: deep risk check", "count": len(finalists)},
               {"stage": "top", "label": "Recommended", "count": len(top)}],
           "longlist": rows, "finalists": finalists, "final_score": final, "team_score": team_score,
           "area_weights": area_w, "area_index": idx,
           "analyst": {"summary": str(an.get("summary") or ""), "reasons": reasons, "passed_over": passed_over, "reasoning": an_reasoning},
           "reports": reports, "market": market, "top": top, "not_chosen": not_chosen,
           "summary": str(ld.get("summary") or ""), "leader_reasoning": ld_reasoning,
           "model": llm.model(), "seconds": round(time.time() - t_start), "created_at": time.strftime("%Y-%m-%d %H:%M"),
           "simulated": "Product catalog, certificates and offers are simulated per supplier (the dataset has no prices)."}
    res["memo"] = memo(res)
    return res


def memo(res: dict) -> str:
    b, by_id = res["brief"], {r["id"]: r for r in res["longlist"]}
    lines = [f"# Sourcing recommendation: {b['quantity']:,} x {b['label']}", "",
             f"*{res['created_at']} · {_kind(b)} · risk lens: {res['lens']} · "
             f"{' → '.join(f'{f['count']:,}' for f in res['funnel'])} suppliers*", ""]
    if res["summary"]:
        lines += [res["summary"], ""]
    for t in res["top"]:
        r = by_id[t["id"]]
        lines += [f"## {t['rank']}. {t['id']} ({r['name']}): {t['role']}", "",
                  f"- Offer: {_money(r['unit_price'])} per unit{' (over target)' if r['over_budget'] else ''}, {_money(r['total'])} total, {r['lead_weeks']} weeks lead time"
                  f"{' (late)' if r['late'] else ''}, {r['warranty_years']}-year warranty",
                  f"- Quality and delivery: quality risk {r['quality_risk']}, delivery rating {r['delivery']:.1f}%, "
                  f"order confirmation {r['confirmation']:.1f}%, order change rate {r['change_rate']:.1f}%",
                  f"- Risk: TRI {r['tri']} ({r['level']}), team risk score {t['team_score']}, final score {t['final_score']} (lower = better)",
                  ""]
        if t["why"]:
            lines += [t["why"], ""]
        if t["pros"]:
            lines += ["Pros: " + "; ".join(t["pros"]), ""]
        if t["cons"]:
            lines += ["Cons: " + "; ".join(t["cons"]), ""]
        if t["red_flags"]:
            lines += ["Red flags: " + "; ".join(f"{f['area']}: {f['issue']}" for f in t["red_flags"]), ""]
        if t["watch"]:
            lines += [f"Watch: {t['watch']}", ""]
    m = res["market"]
    if m.get("signals"):
        lines += ["## Market right now", "", m.get("summary", ""), ""]
        lines += [f"- {s['title']} ({s['date'] or 'recent'}): {s['impact']} [{s['url']}]" for s in m["signals"]]
        lines += [""]
    if res["not_chosen"]:
        lines += ["## Finalists not chosen", ""] + [f"- {x['id']}: {x['reason']}" for x in res["not_chosen"]] + [""]
    lines += [f"*{res['simulated']}*"]
    return "\n".join(lines)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    comp, qty, weeks = (sys.argv[1:] + ["brake_control_unit", "400", "30"])[:3]
    out = run(comp, int(qty), int(weeks), log=lambda s: print(f"[{s.get('agent')}] {s.get('type')}: {s.get('content') or s.get('args')}"))
    print(out["memo"])
