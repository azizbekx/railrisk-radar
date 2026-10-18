"""Supply data, explainable risk scoring and impact propagation."""
import csv
import json
import math
from datetime import date
from functools import lru_cache
from pathlib import Path

import networkx as nx

DATA = Path(__file__).resolve().parent.parent / "data"
TODAY = date(2026, 10, 18)

WEIGHTS = {
    "external": 0.30,
    "single_source": 0.15,
    "financial": 0.15,
    "country": 0.10,
    "delivery": 0.10,
    "quality": 0.10,
    "certification": 0.10,
}
FACTOR_LABELS = {
    "external": "External events (agent)",
    "single_source": "Single-source dependency",
    "financial": "Financial health",
    "country": "Country / geopolitical",
    "delivery": "On-time delivery trend",
    "quality": "Quality (PPM, NCRs)",
    "certification": "Certification status",
}


def band(score: float) -> str:
    return "act now" if score >= 60 else "watch" if score >= 40 else "low"


@lru_cache
def suppliers() -> dict:
    return {s["id"]: s for s in json.loads((DATA / "suppliers.json").read_text())}


@lru_cache
def projects() -> dict:
    return {p["id"]: p for p in json.loads((DATA / "projects.json").read_text())}


@lru_cache
def bom() -> list:
    with open(DATA / "bom.csv") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["share"] = float(r["share"])
        r["unit_cost_eur"] = float(r["unit_cost_eur"])
        r["required_certs"] = r["required_certs"].split(";") if r["required_certs"] else []
    return rows


@lru_cache
def alternatives() -> list:
    with open(DATA / "alternatives.csv") as f:
        return list(csv.DictReader(f))


@lru_cache
def country_risk() -> dict:
    with open(DATA / "country_risk.csv") as f:
        return {r["country"]: {"name": r["name"], "risk": int(r["risk"])} for r in csv.DictReader(f)}


def resolve_supplier(ref: str) -> dict | None:
    """Find a supplier by id or (partial, case-insensitive) name."""
    if not ref:
        return None
    ref = ref.strip()
    if ref.upper() in suppliers():
        return suppliers()[ref.upper()]
    low = ref.lower()
    for s in suppliers().values():
        if low in s["name"].lower():
            return s
    return None


# ---------- graph ----------

@lru_cache
def graph() -> nx.DiGraph:
    """Directed supply graph: tier-2 supplier -> tier-1 supplier -> component -> project."""
    g = nx.DiGraph()
    for s in suppliers().values():
        g.add_node(s["id"], kind="supplier", label=s["name"])
        for t1 in s["feeds"]:
            g.add_edge(s["id"], t1, share=1.0)
    for r in bom():
        comp = f"C:{r['component']}"
        g.add_node(comp, kind="component", label=r["component"])
        g.add_node(r["project_id"], kind="project", label=projects()[r["project_id"]]["name"])
        g.add_edge(r["supplier_id"], comp, share=r["share"])
        g.add_edge(comp, r["project_id"])
    return g


def components_of(sid: str) -> list[dict]:
    """Components a supplier delivers directly (tier 1)."""
    seen = {}
    for r in bom():
        if r["supplier_id"] == sid:
            seen.setdefault(r["component"], {"component": r["component"], "share": r["share"], "projects": set()})
            seen[r["component"]]["projects"].add(r["project_id"])
    return [{**v, "projects": sorted(v["projects"])} for v in seen.values()]


def is_single_source(sid: str) -> bool:
    s = suppliers()[sid]
    if s["tier"] == 2:
        return True  # tier-2 parts in this dataset have no qualified second source
    return any(c["share"] >= 1.0 for c in components_of(sid))


# ---------- scoring ----------

def cert_status(s: dict) -> list[dict]:
    out = []
    required = set()
    for r in bom():
        if r["supplier_id"] == s["id"]:
            required.update(r["required_certs"])
    for name in sorted(required | set(s["certs"])):
        exp = s["certs"].get(name)
        if exp is None:
            out.append({"cert": name, "expiry": None, "days_left": None, "status": "missing"})
            continue
        days = (date.fromisoformat(exp) - TODAY).days
        status = "expired" if days < 0 else "expiring" if days <= 90 else "valid"
        out.append({"cert": name, "expiry": exp, "days_left": days, "status": status})
    return out


def external_score(events: list[dict]) -> float:
    """Combine independent event risks: 1 - prod(1 - p_i), p = severity/5 * confidence * relevance."""
    keep = 1.0
    for e in events or []:
        p = (float(e.get("severity", 1)) / 5) * float(e.get("confidence", 0.5)) * float(e.get("relevance", 1.0))
        keep *= 1 - min(max(p, 0), 0.95)
    return round(100 * (1 - keep), 1)


def score_supplier(sid: str, events: list[dict] | None = None) -> dict:
    s = suppliers()[sid]
    otd = s["otd_6m"]
    recent = sum(otd[-3:]) / 3
    trend = (sum(otd[-3:]) - sum(otd[:3])) / 3  # negative = getting worse
    certs = cert_status(s)
    cert_pts = 0
    for c in certs:
        cert_pts = max(cert_pts, {"expired": 100, "missing": 80, "expiring": 40 + (90 - c["days_left"]) * 0.5 if c["days_left"] is not None else 0, "valid": 0}[c["status"]])

    single = is_single_source(sid)
    dual_major = any(0.5 <= c["share"] < 1.0 for c in components_of(sid))
    factors = {
        "external": external_score(events),
        "single_source": (100 if s["lead_time_weeks"] >= 20 else 70) if single else 50 if dual_major else 15,
        "financial": 100 - s["financial_score"],
        "country": country_risk().get(s["country"], {"risk": 50})["risk"],
        "delivery": min(100, max(0, (97 - recent) * 6 + max(0, -trend) * 8)),
        "quality": min(100, max(0, 25 * math.log10(max(s["quality_ppm"], 1) / 50)) + s["ncr_12m"] * 4),
        "certification": min(100, cert_pts),
    }
    factors = {k: round(v, 1) for k, v in factors.items()}
    total = round(sum(WEIGHTS[k] * v for k, v in factors.items()), 1)
    reasons = []
    if factors["external"] >= 40:
        reasons.append(f"{len(events or [])} external risk signal(s) found by the agent")
    if single:
        reasons.append("sole qualified source")
    if s["financial_score"] < 55:
        reasons.append(f"weak financial health ({s['financial_score']}/100)")
    if factors["country"] >= 50:
        reasons.append(f"high country risk ({country_risk()[s['country']]['name']})")
    if trend <= -3:
        reasons.append(f"on-time delivery falling ({otd[0]}% to {otd[-1]}%)")
    for c in certs:
        if c["status"] == "expired":
            reasons.append(f"{c['cert']} expired {-c['days_left']} days ago")
        elif c["status"] == "expiring":
            reasons.append(f"{c['cert']} expires in {c['days_left']} days")
        elif c["status"] == "missing":
            reasons.append(f"{c['cert']} missing")
    return {"id": sid, "score": total, "band": band(total), "factors": factors, "reasons": reasons,
            "certs": certs, "otd_recent": round(recent, 1), "otd_trend": round(trend, 1)}


def score_all(events_by_supplier: dict | None = None) -> list[dict]:
    events_by_supplier = events_by_supplier or {}
    rows = [score_supplier(sid, events_by_supplier.get(sid)) for sid in suppliers()]
    return sorted(rows, key=lambda r: -r["score"])


# ---------- impact ----------

def trace_impact(sid: str, disruption_weeks: float = 4, capacity_loss: float = 1.0) -> dict:
    """Propagate a disruption at supplier `sid` through the graph to train projects and euros."""
    g = graph()
    s = suppliers()[sid]
    # Tier-1 suppliers affected (self, or customers of a tier-2)
    paths = []  # (tier1_id, component, share)
    t1s = [sid] if s["tier"] == 1 else s["feeds"]
    for t1 in t1s:
        for c in components_of(t1):
            paths.append((t1, c["component"], c["share"], c["projects"]))

    # outage + restart/requalification ramp (longer for long-lead parts)
    disruption_days = disruption_weeks * 7 + 0.25 * s["lead_time_weeks"] * 7 * capacity_loss
    proj_hits = {}
    comp_rows = []
    for t1, comp, share, projs in paths:
        buffer = suppliers()[t1]["stock_days"] + (s["stock_days"] if s["tier"] == 2 else 0) * 0.5
        lost = capacity_loss * share
        # dual-sourced parts: the other source covers part of the gap
        gap_days = max(0.0, disruption_days - buffer) * (lost if share < 1 else capacity_loss)
        comp_rows.append({"component": comp, "via": suppliers()[t1]["name"], "share": share,
                          "buffer_days": round(buffer), "delay_days": round(gap_days)})
        for pid in projs:
            proj_hits.setdefault(pid, []).append((comp, gap_days))

    proj_rows = []
    for pid, hits in proj_hits.items():
        p = projects()[pid]
        delay = max(h[1] for h in hits)
        late = max(0.0, delay - p["slack_days"])
        proj_rows.append({
            "project": pid, "name": p["name"], "customer": p["customer"], "delivery": p["delivery"],
            "components": sorted({h[0] for h in hits}), "delay_days": round(delay),
            "late_days": round(late), "exposure_eur": round(late * p["penalty_per_day_eur"]),
        })
    proj_rows.sort(key=lambda r: -r["exposure_eur"])
    edges = []
    if s["tier"] == 2:
        for t1 in t1s:
            edges.append((s["name"], suppliers()[t1]["name"], 1))
    for t1, comp, share, projs in paths:
        edges.append((suppliers()[t1]["name"], comp, 1))
        for pid in projs:
            edges.append((comp, projects()[pid]["name"], 1))
    return {
        "supplier": s["name"], "supplier_id": sid, "disruption_weeks": disruption_weeks,
        "capacity_loss": capacity_loss, "components": comp_rows, "projects": proj_rows,
        "total_exposure_eur": sum(r["exposure_eur"] for r in proj_rows), "edges": edges,
        "nodes_affected": len(nx.descendants(g, sid)),
    }


def find_alternatives(component: str) -> list[dict]:
    low = component.lower()
    out = [a for a in alternatives() if low in a["component"].lower() or a["component"].lower() in low]
    order = {"Qualified": 0, "In qualification": 1, "Not qualified": 2}
    return sorted(out, key=lambda a: (order.get(a["status"], 3), int(a["qualification_months"])))


def portfolio_summary(scores: list[dict]) -> dict:
    at_risk = [r for r in scores if r["score"] >= 40]
    act = [r for r in scores if r["score"] >= 60]
    single = sum(1 for sid in suppliers() if is_single_source(sid))
    exposure = sum(trace_impact(r["id"], 6)["total_exposure_eur"] for r in act)
    return {"suppliers": len(scores), "watch": len(at_risk) - len(act), "act": len(act),
            "single_source": single, "exposure_eur": exposure}
