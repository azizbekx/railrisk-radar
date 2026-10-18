"""Live supplier tracking: the organisation's real suppliers are watched every day. One worker agent per supplier
searches recent news and extracts dated risk events; Python turns the events into a daily risk time series, a trend
and a 30-day forecast; a leader agent writes the portfolio briefing (outlooks, watchlist, actions).
Python computes every number; the agents find, classify and judge.

    .venv/bin/python -m core.tracking --run | --sample | --show"""
import argparse
import hashlib
import json
import logging
import os
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from core import dataset as ds, llm, team

_log = logging.getLogger("tracking")

ROOT = Path(__file__).resolve().parent.parent / "cache"
STATE = ROOT / "tracking" / "state.json"
DEMO = ROOT / "demo" / "tracking.json"  # tracked seed, read when there is no local state

AREAS = list(team.AGENTS)
HALF_LIFE = 14.0  # days after which an event counts half
POINTS = {1: 3, 2: 6, 3: 10, 4: 16, 5: 24}  # severity -> risk points; a risk_down event counts half, negative
CRITICALITY = {"High": 3, "Medium": 2, "Low": 1}
DEFAULT_BASE = 35.0
MAX_SUPPLIERS, MAX_EVENTS, MAX_RUNS = 30, 200, 30
HISTORY, HORIZON = 30, 30  # days of series / forecast
TREND_DAYS, TREND_PT = 14, 1.0  # least-squares window, pts/week that count as rising or falling
PROB = {"Low": 0.03, "Medium": 0.08, "High": 0.2, "Critical": 0.4}  # fallback 90-day disruption odds per level

# Example portfolio: only companies publicly documented as Siemens Mobility suppliers, each with its source
SAMPLE = [
    {"name": "Knorr-Bremse", "website": "knorr-bremse.com", "country": "Germany", "category": "Braking and entrance systems",
     "criticality": "High", "relationship": "Brakes and entrance systems for Siemens Velaro trains (DB ICE 3neo, Egypt)",
     "source": "https://railway-news.com/knorr-bremse-to-equip-siemens-mobility-trains-for-operation-in-egypt"},
    {"name": "Schaeffler", "website": "schaeffler.com", "country": "Germany", "category": "Axlebox bearings",
     "criticality": "High", "relationship": "Siemens Mobility Supplier Award 2025 for Velaro high-speed axlebox bearings",
     "source": "https://www.afm.es/en/news/schaeffler-wins-siemens-mobility-supplier-award-2025-ndash-axlebox-bearings-enable-new-benchmarks-in-high-speed-trains"},
    {"name": "Hitachi Energy", "website": "hitachienergy.com", "country": "Switzerland", "category": "Traction transformers",
     "criticality": "High", "relationship": "360 traction transformers for Siemens Mobility's Munich S-Bahn trains (2025 order)",
     "source": "https://www.hitachienergy.com/news-and-events/features/2025/01/hitachi-energy-to-supply-360-resibloc-rail-traction-transformers-to-siemens-mobility-for-munich-s-new-s-bahn-trains"},
    {"name": "Voith", "website": "voith.com", "country": "Germany", "category": "Scharfenberg couplers",
     "criticality": "Medium", "relationship": "30-year coupler service contract with Siemens Mobility (Velaro and Desiro fleets)",
     "source": "https://voith.com/corp-en/news-room/press-releases/2021-03-25_vt_voith-expands-service-business-for-railway-couplers.html"},
    {"name": "HÜBNER Group", "website": "hubner-group.com", "country": "Germany", "category": "Gangway systems",
     "criticality": "Medium", "relationship": "Gangway systems for Siemens Velaro and Desiro HC trains",
     "source": "https://www.railvolution.net/news/innotrans-2022-7"},
]

RUN_LOCK = threading.Lock()  # one tracking run at a time (manual "Run now" and the scheduler share it)
_IO = threading.RLock()  # guards read-modify-write of the state file


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(dt: datetime | None = None) -> str:
    return (dt or _now()).strftime("%Y-%m-%d %H:%M")


# ---------- storage ----------

def _empty() -> dict:
    return {"suppliers": [], "leader": None, "runs": []}


def _load() -> dict:
    for f in (STATE, DEMO):
        if f.exists():
            try:
                return {**_empty(), **json.loads(f.read_text())}
            except (OSError, ValueError):
                _log.warning("unreadable tracking state %s", f)
    return _empty()


def _save(state: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_name(STATE.name + ".tmp")
    tmp.write_text(json.dumps(state, default=str))
    os.replace(tmp, STATE)


# ---------- suppliers ----------

def _find(state: dict, sid: str) -> dict:
    for s in state["suppliers"]:
        if s["id"] == sid:
            return s
    raise KeyError(sid)


def add_supplier(name: str, website: str = "", country: str = "", category: str = "", criticality: str = "Medium",
                 dataset_id: str | None = None, relationship: str = "", source: str = "") -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Supplier name is required")
    criticality = (criticality or "Medium").strip().capitalize()
    if criticality not in CRITICALITY:
        raise ValueError("Criticality must be High, Medium or Low")
    sid = ds.resolve(dataset_id) if (dataset_id or "").strip() else None
    if (dataset_id or "").strip() and sid not in ds.df().index:
        raise ValueError(f"Unknown dataset supplier: {dataset_id}")
    with _IO:
        state = _load()
        if len(state["suppliers"]) >= MAX_SUPPLIERS:
            raise ValueError(f"At most {MAX_SUPPLIERS} suppliers can be tracked")
        s = {"id": "T_" + uuid.uuid4().hex[:8], "name": name, "website": (website or "").strip(),
             "country": (country or "").strip(), "category": (category or "").strip(), "criticality": criticality,
             "dataset_id": sid, "relationship": (relationship or "").strip()[:300], "source": (source or "").strip()[:500],
             "added_at": _stamp(), "status": "pending", "last_checked": None,
             "baseline": {a: v[sid] for a, v in team.area_index([sid]).items()} if sid else None,
             "events": [], "signals": [], "sources_checked": 0, "note": "", "error": None, "outlook": None}
        state["suppliers"].append(s)
        _save(state)
    return _supplier_out(s)


def remove_supplier(sid: str):
    with _IO:
        state = _load()
        _find(state, sid)
        state["suppliers"] = [s for s in state["suppliers"] if s["id"] != sid]
        _save(state)


def add_sample() -> dict:
    with _IO:
        have = {s["name"].lower() for s in _load()["suppliers"]}
    for spec in SAMPLE:
        if spec["name"].lower() not in have:
            add_supplier(**spec)
    return portfolio()


# ---------- score math (deterministic) ----------

@lru_cache
def _weights() -> dict:
    w = team.lens_area_weights(ds.TRI_WEIGHTS)
    return {a: v / sum(w.values()) for a, v in w.items()}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _num(v, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if f == f else default  # NaN
    except (TypeError, ValueError):
        return default


def _areas(base: dict, evs: list, day: date) -> dict:
    """Area scores on a day: baseline plus every earlier event, decayed with a 14-day half-life."""
    return {a: _clamp(base[a] + sum(i * 0.5 ** ((day - d).days / HALF_LIFE) for d, ar, i in evs if ar == a and d <= day), 0, 100)
            for a in AREAS}


def _overall(areas: dict) -> float:
    w = _weights()
    return sum(w[a] * areas[a] for a in AREAS)


def _curves(s: dict) -> dict:
    """Series (last 30 days), area series, trend and forecast (next 30 days) of one checked supplier."""
    today = _now().date()
    base = s["baseline"]
    evs = [(date.fromisoformat(e["date"]), e["area"], e["impact"]) for e in s["events"]]
    days = [today - timedelta(days=HISTORY - 1 - i) for i in range(HISTORY)]
    per_day = [_areas(base, evs, d) for d in days]
    overall = [_overall(a) for a in per_day]
    slope = float(np.polyfit(range(TREND_DAYS), overall[-TREND_DAYS:], 1)[0]) * 7
    vol = float(np.std(np.diff(overall)))
    future = [today + timedelta(days=k) for k in range(1, HORIZON + 1)]
    decay = [_overall(_areas(base, evs, d)) for d in future]
    delta = (s.get("outlook") or {}).get("delta_30d")
    shift = _clamp(overall[-1] + _num(delta), 0, 100) - decay[-1] if delta is not None else 0.0  # ramp to the leader's target
    fc = []
    for k, (d, v) in enumerate(zip(future, decay), 1):
        v = _clamp(v + shift * k / HORIZON, 0, 100)
        band = 4 + 0.4 * k ** 0.5 * vol
        fc.append({"date": d.isoformat(), "score": round(v, 1), "low": round(_clamp(v - band, 0, 100), 1),
                   "high": round(_clamp(v + band, 0, 100), 1)})
    return {"areas": {a: round(v, 1) for a, v in per_day[-1].items()}, "overall": overall, "slope": slope,
            "area_series": [{"date": d.isoformat(), **{a: round(v, 1) for a, v in p.items()}} for d, p in zip(days, per_day)],
            "series": [{"date": d.isoformat(), "score": round(v, 1)} for d, v in zip(days, overall)], "forecast": fc}


def _supplier_out(s: dict, detail: bool = False) -> dict:
    """TrackedSupplier (or SupplierDetail) from the stored supplier."""
    out = {k: s[k] for k in ("id", "name", "website", "country", "category", "criticality", "dataset_id", "added_at",
                             "status", "last_checked", "baseline", "note", "error", "outlook")}
    out.update({"relationship": s.get("relationship", ""), "source": s.get("source", "")})
    evs = sorted(s["events"], key=lambda e: (e["date"], e["found_at"]), reverse=True)
    today = _now().date()
    out.update({"score": None, "level": None, "delta_1d": None, "delta_7d": None, "areas": None, "series": [],
                "forecast": [], "trend": None, "slope_per_week": None, "latest_event": evs[0] if evs else None,
                "events_30d": sum(1 for e in evs if e["date"] >= (today - timedelta(days=HISTORY - 1)).isoformat())})
    c = None
    if s["baseline"] and s["status"] != "pending":
        c = _curves(s)
        o = c["overall"]
        slope = c["slope"]
        out.update({"score": round(o[-1], 1), "level": ds.level(o[-1]), "delta_1d": round(o[-1] - o[-2], 1),
                    "delta_7d": round(o[-1] - o[-8], 1), "areas": c["areas"], "series": c["series"],
                    "forecast": c["forecast"], "slope_per_week": round(slope, 2),
                    "trend": "rising" if slope > TREND_PT else "falling" if slope < -TREND_PT else "stable"})
    if detail:
        out.update({"area_series": c["area_series"] if c else [], "events": evs, "signals": s["signals"],
                    "sources_checked": s["sources_checked"]})
    return out


def _blend(rows: list[dict]) -> dict:
    """Criticality-weighted mean (High 3, Medium 2, Low 1) of the suppliers' series and forecasts."""
    rows = [r for r in rows if r["series"]]
    if not rows:
        return {"score": 0, "level": "Low", "delta_7d": 0, "series": [], "forecast": []}
    w = [CRITICALITY[r["criticality"]] for r in rows]

    def mean(key, field):
        return [{"date": rows[0][key][i]["date"], **{f: round(sum(wi * r[key][i][f] for wi, r in zip(w, rows)) / sum(w), 1)
                                                     for f in field}} for i in range(len(rows[0][key]))]
    series, forecast = mean("series", ["score"]), mean("forecast", ["score", "low", "high"])
    score = series[-1]["score"]
    return {"score": score, "level": ds.level(score), "delta_7d": round(score - series[-8]["score"], 1),
            "series": series, "forecast": forecast}


# ---------- worker agent: one per supplier ----------

AREA_ROSTER = "\n".join(f"- {a}: {s['focus']}" for a, s in team.AGENTS.items())

WORKER_SYSTEM = f"""You are a news-monitoring agent for Siemens rail procurement. You watch ONE supplier. Given the
supplier and the recent news search results (numbered articles with title, url, publication date and text), extract
the events that change the supplier's risk of failing to deliver components to a rail OEM.
Risk areas:
{AREA_ROSTER}
Rules:
- Only events about THIS company (the given name, country and category). Ignore namesakes, other companies with a
  similar name and articles that merely mention it in passing.
- Only material supplier risk for a rail OEM: finances and guidance, insolvency, plant fire or outage, strikes, recalls
  and quality problems, lawsuits and fines, sanctions, cyber attacks, delivery delays, ownership changes, geopolitics.
  Good news that lowers risk (new financing, resolved dispute, capacity added) is an event with direction "risk_down".
  Ignore marketing, awards, generic market reports and routine product news.
- An empty events list is fine and often correct. Never invent an event, a url or a date: every event must come from
  one of the given articles and carry that article's exact url.
- severity: 1 minor, 2 noticeable, 3 material, 4 serious (threatens deliveries), 5 severe (stops or may stop supply).
- date: the day the event happened or was reported, YYYY-MM-DD; use the article's publication date when unsure.
Return JSON only:
{{"summary": "one sentence on this supplier's news situation",
 "signals": ["up to 4 short bullet findings, empty if nothing relevant"],
 "baseline": {{{", ".join(f'"{a}": 0-100' for a in AREAS)}}},
 "events": [{{"title": "...", "url": "...", "date": "YYYY-MM-DD", "area": "one of the risk areas above",
            "severity": 1-5, "direction": "risk_up|risk_down", "summary": "one sentence, what happened and why it matters"}}]}}
"baseline" is only required when the input says needs_baseline: your estimate of the supplier's structural risk per
area (0-100, higher = riskier; Low <25, Medium 25-49, High 50-74, Critical >=75) from what you found, and 35 where
you know nothing. Otherwise omit it."""


def _parse_date(x) -> date | None:
    x = str(x or "").strip()
    if not x:
        return None
    try:
        return date.fromisoformat(x[:10])
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(x)
    except (TypeError, ValueError):
        return None
    return (dt.astimezone(timezone.utc) if dt.tzinfo else dt).date()


def _area(x) -> str | None:
    x = str(x or "").strip().lower()
    return next((a for a in AREAS if a.lower() == x or a.lower().split()[0] == x.split(" ")[0]), None) if x else None


def _event_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:10]


def _clean_events(raw, results: list[dict], start: date, today: date, found_at: str) -> list[dict]:
    """Keep only well-formed events that point at a real search result and fall inside the window."""
    by_url = {r["url"]: r for r in results}
    out = {}
    for e in raw if isinstance(raw, list) else []:
        if not isinstance(e, dict):
            continue
        url = str(e.get("url") or "").strip()
        area = _area(e.get("area"))
        if url not in by_url or not area:
            continue
        art = by_url[url]
        d = _parse_date(e.get("date")) or _parse_date(art.get("date")) or today
        if d > today or d < start:
            continue
        sev = int(_clamp(round(_num(e.get("severity"), 2)), 1, 5))
        up = "down" not in str(e.get("direction") or "").lower()
        out.setdefault(_event_id(url), {
            "id": _event_id(url), "date": d.isoformat(), "title": str(e.get("title") or art.get("title") or url)[:200],
            "url": url, "source": urlparse(url).netloc.removeprefix("www."), "area": area, "severity": sev,
            "impact": float(POINTS[sev]) if up else -POINTS[sev] / 2,
            "summary": str(e.get("summary") or "")[:400], "found_at": found_at})
    return list(out.values())


def _baseline(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {a: round(_clamp(_num(raw.get(a), DEFAULT_BASE), 0, 100), 1) for a in AREAS}


def _apply(s: dict, res: dict) -> dict:
    """Merge a worker result into a stored supplier (in place)."""
    s["status"], s["error"] = res["status"], res.get("error")
    if res["status"] != "ok":
        return s
    s.update({"last_checked": res["checked"], "note": res["note"], "signals": res["signals"],
              "sources_checked": res["sources_checked"]})
    if res.get("baseline") and not s.get("baseline"):
        s["baseline"] = res["baseline"]
    known = {e["id"] for e in s["events"]}
    s["events"] = sorted(s["events"] + [e for e in res["events"] if e["id"] not in known],
                         key=lambda e: (e["date"], e["found_at"]))[-MAX_EVENTS:]
    return s


def _work(s: dict, say) -> dict:
    """Search the news about one supplier and extract its risk events. Returns a result for _apply."""
    name, today = s["name"], _now().date()
    last = _parse_date(s["last_checked"])
    days = HISTORY if last is None else int(_clamp((today - last).days, 2, HISTORY))
    start, checked = today - timedelta(days=days), _stamp()
    queries = [f'"{name}"', f'"{name}" {s["category"]} lawsuit OR strike OR recall OR insolvency OR sanctions OR fire OR delay'.replace("  ", " "),
               f'"{name}" results OR guidance OR profit warning OR financing']
    say({"agent": name, "type": "status", "content": f"Checking news of the last {days} days"})
    results, seen, errors = [], set(), []
    for q in queries:
        say({"agent": name, "type": "tool_call", "name": "search_news", "args": {"query": q, "days": days}})
        try:
            found = [r for r in llm.search_news(q, days=days, max_results=5) if r.get("url") and r["url"] not in seen]
        except Exception as e:
            errors.append(str(e))
            say({"agent": name, "type": "error", "content": f"search failed: {e}"})
            continue
        seen.update(r["url"] for r in found)
        results += found
        say({"agent": name, "type": "tool_result", "name": "search_news",
             "content": [{"title": r["title"] or r["url"], "url": r["url"]} for r in found]})
    if not results and errors:
        raise RuntimeError(f"search failed: {errors[0]}")
    need_base = not s.get("baseline")
    res = {"status": "ok", "error": None, "checked": checked, "sources_checked": len(results), "events": [],
           "signals": [], "note": "No recent news found.", "baseline": _baseline(None) if need_base else None}
    if results:
        say({"agent": name, "type": "status", "content": f"Reading {len(results)} articles"})
        data, _ = team._ask_json(WORKER_SYSTEM, json.dumps({
            "today": today.isoformat(), "window": f"{start.isoformat()} to {today.isoformat()}", "needs_baseline": need_base,
            "supplier": {k: s.get(k, "") for k in ("name", "website", "country", "category", "relationship")},
            "articles": [{"n": i + 1, "title": r["title"], "url": r["url"], "published": r.get("date") or "",
                          "text": r["content"]} for i, r in enumerate(results)]}), 4000)
        res.update({"note": str(data.get("summary") or "No notable news.")[:300],
                    "signals": [str(x)[:200] for x in (data.get("signals") or [])[:4]] if isinstance(data.get("signals"), list) else [],
                    "events": _clean_events(data.get("events"), results, start, today, checked)})
        if need_base:
            res["baseline"] = _baseline(data.get("baseline"))
    return res


# ---------- leader agent ----------

LEADER_SYSTEM = f"""You lead a supplier-monitoring team for Siemens rail procurement. One worker agent per supplier
searched the latest news; Python turned the events into a risk score per supplier (0-100, higher = riskier; Low <25,
Medium 25-49, High 50-74, Critical >=75), a 7-day change and a trend. You get every supplier with its criticality
(High/Medium/Low, how hard it is to replace), score, area scores, trend, latest events and the worker's summary.
Write the briefing for the buyer. Use only the given facts and numbers; never invent events.
Return JSON only:
{{"headline": "one sentence: the most important thing the buyer should know today",
 "summary_md": "markdown, 150-300 words: portfolio picture, what changed, the 2-3 suppliers that matter most and why, concrete next steps",
 "outlooks": {{"<supplier id>": {{"direction": "rising|stable|falling", "delta_30d": -20..20 (expected score change over 30 days),
              "confidence": "high|medium|low", "reason": "one sentence", "disruption_prob_90d": 0-1}}}},
 "watchlist": [{{"id": "<supplier id>", "reason": "one sentence with the evidence", "action": "one concrete action for the buyer",
                "predicted_level": "Low|Medium|High|Critical (expected level in 30 days)"}}]}}
Give an outlook for every supplier. The watchlist holds only suppliers that need attention (at most 5, most urgent first),
and may be empty. Weigh criticality: a High-criticality supplier with a rising trend matters more. Calm news means
stable and a low disruption probability."""


def _fallback_brief(rows: list[dict]) -> dict:
    """Brief from Python numbers alone, used when the leader call fails."""
    outlooks = {}
    for r in rows:
        delta = round(_clamp(r["slope_per_week"] * 4, -20, 20), 1)
        outlooks[r["id"]] = {"direction": r["trend"], "delta_30d": delta, "confidence": "low",
                             "reason": f"Extrapolated from the {r['trend']} trend of the last {TREND_DAYS} days.",
                             "disruption_prob_90d": PROB[r["level"]]}
    rising = [r for r in rows if r["trend"] == "rising"]
    top = max(rows, key=lambda r: r["score"])
    watch = sorted((r for r in rows if r["level"] in ("High", "Critical") or r["trend"] == "rising"),
                   key=lambda r: (r["score"] + 5 * (r["trend"] == "rising")) * CRITICALITY[r["criticality"]], reverse=True)[:5]
    lines = [f"- **{r['name']}**: score {r['score']} ({r['level']}), {r['delta_7d']:+.1f} in 7 days, {r['trend']}, "
             f"{r['events_30d']} event(s) in 30 days" for r in sorted(rows, key=lambda r: -r["score"])]
    return {"headline": f"{len(rows)} suppliers tracked, {len(rising)} rising; highest risk is {top['name']} at {top['score']}.",
            "summary_md": "The leader agent was unavailable, so this briefing is computed from the numbers only.\n\n" + "\n".join(lines),
            "outlooks": outlooks,
            "watchlist": [{"id": r["id"], "reason": f"Score {r['score']} ({r['level']}), {r['trend']}.",
                           "action": "Review the latest events and contact the supplier." if r["level"] in ("High", "Critical")
                           else "Keep watching; check again after the next run.",
                           "predicted_level": ds.level(_clamp(r["score"] + outlooks[r["id"]]["delta_30d"], 0, 100))} for r in watch]}


def _clean_brief(data: dict, rows: list[dict]) -> dict:
    """Validate the leader's JSON against the real suppliers; anything missing or invalid falls back to Python numbers."""
    base = _fallback_brief(rows)
    by_id = {r["id"]: r for r in rows}
    raw = data.get("outlooks") if isinstance(data.get("outlooks"), dict) else {}
    outlooks = {}
    for sid, r in by_id.items():
        o = raw.get(sid) if isinstance(raw.get(sid), dict) else None
        if not o:
            outlooks[sid] = base["outlooks"][sid]
            continue
        direction = str(o.get("direction") or "").lower()
        conf = str(o.get("confidence") or "").lower()
        outlooks[sid] = {
            "direction": direction if direction in ("rising", "stable", "falling") else r["trend"],
            "delta_30d": round(_clamp(_num(o.get("delta_30d")), -20, 20), 1),
            "confidence": conf if conf in ("high", "medium", "low") else "low",
            "reason": str(o.get("reason") or "")[:400],
            "disruption_prob_90d": round(_clamp(_num(o.get("disruption_prob_90d"), PROB[r["level"]]), 0, 1), 2)}
    watch, seen = [], set()
    for w in data.get("watchlist") if isinstance(data.get("watchlist"), list) else []:
        sid = w.get("id") if isinstance(w, dict) else None
        if sid not in by_id or sid in seen:
            continue
        seen.add(sid)
        lvl = str(w.get("predicted_level") or "").capitalize()
        watch.append({"id": sid, "reason": str(w.get("reason") or "")[:400], "action": str(w.get("action") or "")[:400],
                      "predicted_level": lvl if lvl in ds.LEVELS else ds.level(_clamp(by_id[sid]["score"] + outlooks[sid]["delta_30d"], 0, 100))})
    headline = str(data.get("headline") or "").strip()
    summary = str(data.get("summary_md") or "").strip()
    return {"headline": headline or base["headline"], "summary_md": summary or base["summary_md"],
            "outlooks": outlooks, "watchlist": watch[:5]}


def _lead(pairs: list[tuple[dict, dict]], say) -> tuple[dict, str]:
    """pairs: (stored supplier, TrackedSupplier) of every checked supplier. Returns (brief, model name)."""
    rows = [o for _, o in pairs if o["score"] is not None]
    payload = [{"id": o["id"], "name": o["name"], "criticality": o["criticality"], "category": o["category"],
                "country": o["country"], "score": o["score"], "level": o["level"], "delta_7d": o["delta_7d"],
                "slope_per_week": o["slope_per_week"], "trend": o["trend"], "area_scores": o["areas"],
                "latest_events": [{k: e[k] for k in ("date", "title", "area", "severity", "impact", "summary")}
                                  for e in sorted(s["events"], key=lambda e: e["date"])[-5:][::-1]],
                "worker_summary": o["note"]} for s, o in pairs if o["score"] is not None]
    try:
        data, _ = team._ask_json(LEADER_SYSTEM, json.dumps({"today": _now().date().isoformat(), "suppliers": payload}), 5000)
        brief = _clean_brief(data, rows)
    except Exception as e:
        say({"agent": "Leader", "type": "error", "content": f"briefing failed, using the computed brief: {e}"})
        brief = _fallback_brief(rows)
    try:
        model = llm.model()
    except Exception:
        model = ""
    return brief, model


# ---------- the run ----------

def run(ids: list[str] | None = None, trigger: str = "manual", log=None) -> dict:
    """Check the given tracked suppliers (default all): workers in parallel, then the leader's briefing."""
    say = log or (lambda _: None)
    if not RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("A tracking run is already in progress")
    try:
        started = _stamp()
        with _IO:
            targets = [dict(s, events=list(s["events"])) for s in _load()["suppliers"] if not ids or s["id"] in ids]
        if not targets:
            raise ValueError("No suppliers to track")
        say({"agent": "Leader", "type": "thought", "content": f"Dispatching {len(targets)} worker agents"})

        def worker(s):
            try:
                res = _work(s, say)
                o = _supplier_out(_apply(dict(s, events=list(s["events"])), res))
                n = len(res["events"])
                new = sum(1 for e in res["events"] if e["id"] not in {x["id"] for x in s["events"]})
                say({"agent": s["name"], "type": "done",
                     "content": f"Score {o['score']} ({o['delta_7d']:+.1f} in 7 days), {new} new event{'s' * (new != 1)}"
                     if o["score"] is not None else f"{n} events found"})
            except Exception as e:
                res = {"status": "error", "error": str(e)[:300]}
                say({"agent": s["name"], "type": "error", "content": f"Worker failed: {e}"})
            return s["id"], res

        with llm.ContextPool(4) as ex:
            results = dict(ex.map(worker, targets))

        with _IO:  # merge into the current state: suppliers may have been added or removed meanwhile
            state = _load()
            before = {s["id"]: {e["id"] for e in s["events"]} for s in state["suppliers"]}
            for s in state["suppliers"]:
                if s["id"] in results:
                    _apply(s, results[s["id"]])
            new_events = sum(len({e["id"] for e in s["events"]} - before[s["id"]]) for s in state["suppliers"] if s["id"] in results)
            errors = sum(1 for r in results.values() if r["status"] != "ok")
            _save(state)

        pairs = [(s, _supplier_out(s)) for s in state["suppliers"]]
        pairs = [(s, o) for s, o in pairs if o["score"] is not None]
        leader = None
        if pairs:
            say({"agent": "Leader", "type": "thought",
                 "content": f"{len(results) - errors} workers reported, {new_events} new events. Writing the briefing"})
            brief, model = _lead(pairs, say)
            with _IO:
                state = _load()
                for s in state["suppliers"]:
                    s["outlook"] = brief["outlooks"].get(s["id"], s.get("outlook"))
                names = {s["id"]: s["name"] for s in state["suppliers"]}
                leader = {"created_at": _stamp(), "model": model, "headline": brief["headline"], "summary_md": brief["summary_md"],
                          "watchlist": [w for w in brief["watchlist"] if w["id"] in names]}
                state["leader"] = leader
                _save(state)
            say({"agent": "Leader", "type": "done", "content": f"Briefing ready: {len(leader['watchlist'])} suppliers on the watchlist"})
        else:
            say({"agent": "Leader", "type": "error", "content": "No supplier has data yet, so there is nothing to brief"})
        with _IO:
            state = _load()
            state["runs"] = ([{"started_at": started, "finished_at": _stamp(), "trigger": trigger, "suppliers": len(results),
                               "new_events": new_events, "errors": errors}] + state["runs"])[:MAX_RUNS]
            _save(state)
    finally:
        RUN_LOCK.release()
    return portfolio()


# ---------- read side ----------

def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "off", "")


def _hour() -> int:
    try:
        return int(_clamp(int(os.getenv("TRACKING_HOUR", "6")), 0, 23))
    except ValueError:
        return 6


def _schedule(state: dict) -> dict:
    enabled, now = _flag("TRACKING_DAILY", "1"), _now()
    last = next((r["finished_at"] for r in state["runs"] if r.get("finished_at")), None)
    nxt = None
    if enabled and state["suppliers"]:
        due = now.replace(hour=_hour(), minute=0, second=0, microsecond=0)
        if last and last[:10] >= now.date().isoformat():
            due += timedelta(days=1)
        nxt = _stamp(due)
    return {"enabled": enabled, "hour_utc": _hour(), "next_run": nxt, "last_run": last}


def portfolio() -> dict:
    with _IO:
        state = _load()
    outs = [_supplier_out(s) for s in state["suppliers"]]
    outs.sort(key=lambda o: (o["score"] is None, -(o["score"] or 0)))
    leader = None
    if state["leader"]:
        names = {o["id"]: o["name"] for o in outs}
        leader = {**state["leader"], "portfolio": _blend(outs),
                  "watchlist": [{"id": w["id"], "name": names[w["id"]], **{k: w[k] for k in ("reason", "action", "predicted_level")}}
                                for w in state["leader"]["watchlist"] if w["id"] in names]}
    return {"suppliers": outs, "leader": leader, "runs": state["runs"], "schedule": _schedule(state),
            "running": RUN_LOCK.locked(), "keys": {k: v for k, v in llm.keys_status().items() if k in ("llm", "tavily")}}


def detail(sid: str) -> dict:
    with _IO:
        return _supplier_out(_find(_load(), sid), detail=True)


# ---------- daily scheduler ----------

_THREAD: threading.Thread | None = None


def _due() -> bool:
    keys, now = llm.keys_status(), _now()
    if not (_flag("TRACKING_DAILY", "1") and keys["llm"] and keys["tavily"]) or now.hour < _hour():
        return False
    with _IO:
        state = _load()
    last = next((r["finished_at"] for r in state["runs"] if r.get("finished_at")), "")
    return bool(state["suppliers"]) and last[:10] < now.date().isoformat() and not RUN_LOCK.locked()


def _loop(every: int):
    while True:
        try:
            if _due():
                _log.info("daily tracking run")
                run(trigger="schedule")
        except Exception:
            _log.exception("scheduled tracking run failed")
        threading.Event().wait(every)


def start_scheduler(every: int = 600):
    """Daemon thread that wakes every 10 minutes and starts the daily run once it is due. Safe to call twice."""
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return
    _THREAD = threading.Thread(target=_loop, args=(every,), daemon=True, name="tracking-scheduler")
    _THREAD.start()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[-1])
    ap.add_argument("--run", action="store_true", help="check all suppliers now (for an external cron)")
    ap.add_argument("--sample", action="store_true", help="add the sample portfolio of 6 rail suppliers")
    ap.add_argument("--show", action="store_true", help="print the portfolio")
    a = ap.parse_args()
    if a.sample:
        add_sample()
    if a.run:
        run(trigger="manual", log=lambda s: print(f"[{s['agent']}] {s['type']}: {s.get('content') or s.get('args') or ''}"))
    if a.show or not (a.sample or a.run):
        p = portfolio()
        if p["leader"]:
            print(p["leader"]["headline"], "\n")
        for o in p["suppliers"]:
            print(f"{o['name']:<18} {o['status']:<8} score {o['score']}  {o['level']}  7d {o['delta_7d']}  {o['trend']}  events30d {o['events_30d']}")
