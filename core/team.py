"""Agent team for the final supplier choice: a leader agent briefs four specialist agents, which analyse the shortlist
at the same time, each from one risk angle; the leader then weighs their reports into a decision and a memo.
Python computes every number (area indices, team scores); the agents judge, explain and design their own chart."""
import json
import re
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor

from core import dataset as ds, llm
from core.fmt import eur

# Each specialist owns a slice of the 18 TRI scores (every score exactly once) plus related operational metrics
AGENTS = {
    "Financial": {
        "icon": "💶", "columns": ["Financial_Health_Score", "Credit_Rating_Score", ds.PO],
        "focus": "financial stability, liquidity, bankruptcy risk and creditworthiness, and how much purchase volume is at stake",
        "chart": {"kind": "scatter", "columns": ["Financial_Health_Score", "Credit_Rating_Score"]}},
    "Operations & Quality": {
        "icon": "🏭", "columns": ["Operational_Resilience_Score", "Quality_Risk_Score", "Sub_Tier_Visibility_Score",
                                 "Digital_Security_Score", "Industry_Benchmark_Score", "Supplier Delivery Rating",
                                 "Order Confirmation Rate", "Order Change Rate", "Sourcing Risk Level", "Supply Chain Complexity"],
        "focus": "production and logistics resilience, product quality, sub-tier visibility, cyber exposure, delivery "
                 "performance and how hard the supplier is to replace",
        "chart": {"kind": "scatter", "columns": ["Quality_Risk_Score", "Supplier Delivery Rating"]}},
    "Compliance & ESG": {
        "icon": "⚖️", "columns": ["Compliance_Risk_Score", "Governance_Risk_Score", "Safety_Incident_Score",
                                 "Labor_Stability_Score", "ESG_Performance_Score"],
        "focus": "lawsuits and regulatory fines, governance and ethics, safety incidents, labour disputes and ESG performance",
        "chart": {"kind": "heatmap"}},
    "Geopolitics & Reputation": {
        "icon": "🌍", "columns": ["Geopolitical_Risk_Score", "Political_Stability_Score", "Environmental_Exposure_Score",
                                 "Media_Sentiment_Score", "Market_Sentiment_Score", "External_Intelligence_Score"],
        "focus": "geopolitical and political instability, natural hazard exposure, and media, market and third-party "
                 "intelligence signals",
        "chart": {"kind": "radar"}},
}
for _a in AGENTS.values():
    _a["scores"] = [c for c in _a["columns"] if c in ds.TRI_WEIGHTS]
    _a["chart"].setdefault("columns", _a["scores"])


def chart_columns(area: str) -> list[str]:
    """Columns an agent may put in its chart: its numeric metrics plus the official TRI."""
    return [c for c in AGENTS[area]["columns"] if c not in ds.CATEGORICAL] + ["Total_Risk_Index"]


def area_index(ids: list[str]) -> dict:
    """Per area and supplier: TRI-weighted average of the area's scores (0-100, higher = riskier)."""
    d = ds.df().loc[ids]
    out = {}
    for a, spec in AGENTS.items():
        w = {c: ds.TRI_WEIGHTS[c] for c in spec["scores"]}
        out[a] = {sid: round(float(sum(d.at[sid, c] * v for c, v in w.items()) / sum(w.values())), 1) for sid in ids}
    return out


def _norm(w, fallback: dict | None = None) -> dict:
    vals = {}
    for a in AGENTS:
        try:
            vals[a] = max(float((w or {}).get(a, 0)), 0.0)
        except (TypeError, ValueError):
            vals[a] = 0.0
    total = sum(vals.values())
    if not total:
        return fallback or {a: round(1 / len(AGENTS), 3) for a in AGENTS}
    return {a: round(v / total, 3) for a, v in vals.items()}


def lens_area_weights(weights: dict) -> dict:
    """Default area weights: the share of the buyer's risk lens that falls into each area."""
    w = ds.normalize_weights(weights)
    return _norm({a: sum(w.get(c, 0) for c in spec["scores"]) for a, spec in AGENTS.items()})


def _rank(col: str, v) -> str:
    """Plain-language rank among all suppliers; 'safer than 95%' reads unambiguously, 'riskier than 5%' does not."""
    s = ds.df()[col]
    good = col in ds.HIGHER_IS_BETTER
    riskier = float(((s > v) if good else (s < v)).mean() * 100)
    safer = float(((s < v) if good else (s > v)).mean() * 100)
    return f"riskier than {riskier:.0f}% of suppliers" if riskier >= safer else f"safer than {safer:.0f}% of suppliers"


def _fmt(col: str, v) -> str:
    if col in ds.CATEGORICAL:
        return str(v)
    if col == ds.PO:
        return eur(float(v))
    if col in ds.TRI_WEIGHTS:
        return f"{int(v)} ({ds.level(v)}, {_rank(col, v)})"
    return f"{float(v):.1f}% ({_rank(col, v)})"


def area_facts(area: str, ids: list[str], idx: dict) -> dict:
    d, mu, cols = ds.df(), ds.means(), AGENTS[area]["columns"]
    return {"area_risk_index": "TRI-weighted average of this area's risk scores, 0-100, higher = riskier",
            "dataset_average": {c: eur(mu[c]) if c == ds.PO else round(float(mu[c]), 1) for c in cols if c not in ds.CATEGORICAL},
            "suppliers": [{"id": sid, "area_risk_index": idx[area][sid], **{c: _fmt(c, d.at[sid, c]) for c in cols}}
                          for sid in ids]}


def _reasoning(msg) -> str:
    """Nemotron on Token Factory returns its reasoning separately from the answer; shown as the agent's thinking."""
    r = getattr(msg, "reasoning_content", None) or (getattr(msg, "model_extra", None) or {}).get("reasoning_content")
    return (r or "").strip()[:4000]


def _ask_json(system: str, user: str, max_tokens: int = 5000) -> tuple[dict, str]:
    msg = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                   temperature=0.1, max_tokens=max_tokens)
    try:
        data = llm.extract_json(msg.content)
    except ValueError:
        data = llm.ask_json(system, user, max_tokens=max_tokens)
    return (data if isinstance(data, dict) else {}), _reasoning(msg)


# ---------- prompts ----------

ROSTER = "\n".join(f"- {a}: {s['focus']}" for a, s in AGENTS.items())

LEADER_PLAN = f"""You lead a team of four specialist risk agents that helps a Siemens rail procurement buyer pick one
supplier from a shortlist. The agents:
{ROSTER}
Given the buying context and default area weights derived from the buyer's risk lens, decide how much each area
should count for THIS purchase, and brief each agent in one sentence on what matters most in its area.
Return JSON only:
{{"weights": {{{", ".join(f'"{a}": 0-1' for a in AGENTS)}}},
 "why": "one sentence explaining the weighting",
 "briefs": {{{", ".join(f'"{a}": "..."' for a in AGENTS)}}}}}
Weights sum to 1. Keep the defaults when the context gives no reason to shift them. For example, safety-critical
parts push Operations & Quality and Compliance & ESG up; long frame contracts push Financial up."""


def specialist_prompt(area: str) -> str:
    return f"""You are the {area} agent in a supplier selection team for Siemens rail procurement. Judge the shortlist
ONLY on {AGENTS[area]['focus']}; other agents cover the rest. Risk scores run 0-100, higher = riskier (Low <25,
Medium 25-49, High 50-74, Critical >=75). Delivery and confirmation rates: higher = better; order change rate: higher
= worse. "safer/riskier than X% of suppliers" compares with all 10,000 suppliers in the dataset. Purchase Order
Volume is what we already spend with the supplier: financial exposure, not a sign of quality.
Use only the facts given and quote their numbers. Return JSON only:
{{"best": "supplier ID you would pick on your area alone", "worst": "supplier ID",
 "verdict": "one sentence for the team leader",
 "findings": ["2-4 short bullets, each with numbers"],
 "red_flags": [{{"supplier": "ID", "issue": "short, with the number"}}],
 "confidence": "high|medium|low",
 "chart": {{"kind": "bars|grouped_bars|scatter|radar|heatmap", "columns": ["dataset column names from the facts"],
           "suppliers": ["IDs to show; empty = all"], "title": "the point the chart makes"}}}}
Design the simplest chart that proves your verdict: bars = one column ranked, grouped_bars = 2-5 columns side by
side, scatter = two columns against each other with all 10,000 suppliers in the background, radar = 3+ risk scores
as a profile, heatmap = suppliers x risk scores. radar and heatmap take risk scores only; area_risk_index is not a
chartable column. red_flags may be empty."""


LEADER_VERDICT = """You lead a supplier selection team for Siemens rail procurement. Four specialist agents analysed
the shortlist, each from one risk angle. You get the agreed area weights, the team score per supplier (weighted
average of the four area risk indices, 0-100, lower = better, computed exactly) and each agent's report. Decide.
Pick the lowest team score unless a red flag in a heavily weighted area is a stated reason to overrule it.
First line exactly: PICK: <supplier ID>
Then markdown, about one page:
## Recommendation (1-2 sentences: the supplier and why)
## What the agents found (one bullet per agent: its pick and the key numbers)
## Where the agents disagree and how you resolved it
## Risks we accept and how we mitigate them (concrete contractual or operational measures for a rail component supplier)
## Next steps (3 bullets)
Quote only numbers from the input. Scores: higher = riskier. Purchase order volume is exposure, never a strength."""

PICK_RE = re.compile(r"PICK:\s*\**\s*(SUPP[_\s-]?\d+)", re.I)


# ---------- the run ----------

def run(ids: list[str], context: str, lens_name: str, lens_weights: dict, log=None) -> dict:
    say = log or (lambda _: None)
    ids = list(ids)
    ctx = context or "not given"
    idx = area_index(ids)
    defaults = lens_area_weights(lens_weights)

    # 1. leader: weight the areas for this purchase and brief the specialists
    say({"agent": "Leader", "type": "thought", "content": f"Planning for {len(ids)} suppliers, risk lens *{lens_name}*"})
    try:
        plan, plan_reasoning = _ask_json(LEADER_PLAN, json.dumps(
            {"buying_context": ctx, "shortlist": ids, "risk_lens": lens_name, "default_weights": defaults}), 3000)
    except Exception as e:
        say({"agent": "Leader", "type": "error", "content": f"planning failed, using the lens weights: {e}"})
        plan, plan_reasoning = {}, ""
    weights = _norm(plan.get("weights"), defaults)
    briefs = plan.get("briefs") if isinstance(plan.get("briefs"), dict) else {}
    say({"agent": "Leader", "type": "thought",
         "content": "Weights " + ", ".join(f"{a} **{w:.0%}**" for a, w in weights.items()) + ". Briefing 4 agents in parallel"})

    # 2. specialists, in parallel
    def specialist(area):
        t0 = time.time()
        say({"agent": area, "type": "status",
             "content": f"Reading {len(AGENTS[area]['columns'])} metrics for {len(ids)} suppliers"})
        brief = str(briefs.get(area) or "")
        try:
            rep, reasoning = _ask_json(specialist_prompt(area), json.dumps(
                {"buying_context": ctx, "leader_brief": brief, "weight_in_decision": weights[area],
                 **area_facts(area, ids, idx)}, default=str))
        except Exception as e:
            rep, reasoning = {"verdict": f"Agent failed: {e}", "error": str(e)}, ""
        best = ds.resolve(rep.get("best"))
        rep["best"] = best if best in ids else min(ids, key=idx[area].get)
        rep.update({"brief": brief, "reasoning": reasoning, "seconds": round(time.time() - t0, 1)})
        say({"agent": area, "type": "error" if "error" in rep else "done",
             "content": f"Picks **{rep['best']}**. {rep.get('verdict', '')}"})
        return area, rep

    with ThreadPoolExecutor(len(AGENTS)) as ex:
        reports = dict(ex.map(specialist, AGENTS))

    # 3. leader: weigh the reports and decide
    team = {sid: round(sum(weights[a] * idx[a][sid] for a in AGENTS), 1) for sid in ids}
    ranking = sorted(ids, key=lambda s: (team[s], int(ds.df().at[s, "Total_Risk_Index"])))
    say({"agent": "Leader", "type": "thought",
         "content": f"Weighing 4 reports. Lowest team score: **{ranking[0]}** ({team[ranking[0]]})"})
    verdict_input = {
        "buying_context": ctx, "risk_lens": lens_name, "area_weights": weights, "weighting_reason": plan.get("why", ""),
        "team_score_ranking": [{"id": s, "team_score": team[s], "TRI": int(ds.df().at[s, "Total_Risk_Index"]),
                                "area_risk_index": {a: idx[a][s] for a in AGENTS}} for s in ranking],
        "agent_reports": {a: {k: r.get(k) for k in ("best", "worst", "verdict", "findings", "red_flags", "confidence")}
                          for a, r in reports.items()}}
    try:
        msg = llm.chat([{"role": "system", "content": LEADER_VERDICT},
                        {"role": "user", "content": json.dumps(verdict_input, default=str)}], max_tokens=6000)
        text, verdict_reasoning = llm.clean(msg.content), _reasoning(msg)
    except Exception as e:
        say({"agent": "Leader", "type": "error", "content": f"verdict failed: {e}"})
        text, verdict_reasoning = f"The leader could not write a verdict ({e}). Lowest team score: **{ranking[0]}**.", ""
    m = PICK_RE.search(text)
    pick = ds.resolve(m.group(1)) if m else None
    pick = pick if pick in ids else ranking[0]
    body = re.sub(r"^.*PICK:.*\n?", "", text, count=1, flags=re.M).strip()
    say({"agent": "Leader", "type": "done", "content": f"Verdict: **{pick}**"})
    header = (f"# Supplier selection memo: {pick}\n\n*{time.strftime('%d %b %Y')} · shortlist of {len(ids)} · "
              f"risk lens: {lens_name}" + (f" · context: {context}" if context else "") +
              " · decided by a leader agent with 4 specialist agents*\n\n")
    return {"ids": ids, "context": context, "lens": lens_name, "weights": weights, "default_weights": defaults,
            "why": plan.get("why", ""), "area_index": idx, "team_score": team, "ranking": ranking,
            "reports": reports, "pick": pick, "memo": header + body, "model": llm.model(),
            "leader_reasoning": "\n\n---\n\n".join(r for r in (plan_reasoning, verdict_reasoning) if r),
            "created_at": time.strftime("%Y-%m-%d %H:%M")}


def flow_dot(res: dict) -> str:
    """Graphviz diagram of the run: buyer -> leader -> 4 specialists (with weights and picks) -> verdict."""
    def q(s):
        return str(s).replace('"', "'")
    ctx = "\\n".join(textwrap.wrap(q(res.get("context") or "no buying context given"), 26)[:3])
    out = ['digraph { rankdir=LR; bgcolor="transparent"; nodesep=0.22; ranksep=0.45;',
           'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, color="#c9d1cc", fillcolor="#f4f6f5"];',
           'edge [color="#8a9a92", fontname="Helvetica", fontsize=10];',
           f'buyer [label="Buyer\\n{ctx}", fillcolor="#e8eef3"];',
           'plan [label="Leader agent\\nweights areas,\\nbriefs the team", fillcolor="#fff4dd"];',
           f'verdict [label="Leader verdict\\n{res["pick"]}", fillcolor="#dff0e3", color="#2f8a4e", penwidth=2];',
           'buyer -> plan;']
    for i, (a, rep) in enumerate(res["reports"].items()):
        agree = rep.get("best") == res["pick"]
        out += [f'a{i} [label="{q(a)}\\npicks {rep.get("best", "?")}"' + (', color="#2f8a4e", penwidth=2' if agree else "") + "];",
                f'plan -> a{i} [label="{res["weights"][a]:.0%}"];', f"a{i} -> verdict;"]
    return "\n".join(out + ["}"])
