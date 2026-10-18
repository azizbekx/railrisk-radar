# RailRisk Radar

Agentic supplier risk intelligence for rolling stock. Built for the **Siemens: Supplier Risk Intelligence** challenge at Nebius Build Week (Berlin, 18 Oct 2026).

A train is built from thousands of parts, and many have only one qualified supplier. Rail certification (EN 15085-2 welding, EN 45545-2 fire safety, ISO/TS 22163, EN 50155) makes switching take 12–24 months. A late bogie frame or a missing power semiconductor stops a train worth tens of millions of euros and triggers contract penalties.

RailRisk Radar watches the world for events that threaten suppliers, traces each one through the bill of materials to the trains it would delay, puts a euro figure on it, and recommends what to do.

## What it does

| Tab | What happens |
|---|---|
| **Overview** | Risk map of 32 tier-1 and tier-2 suppliers, top-10 scores broken down by factor, ranked watch list, one-click **agent risk scan** |
| **Supplier deep dive** | Explainable 0–100 score, delivery trend, certificate expiry, cited news events, outage simulator (supplier → component → train → €), AI mitigation plan with a drafted supplier email |
| **What-if scenario** | Type any disruption ("flooding in Penang"). The LLM maps it to affected suppliers and the supply graph traces the cascade to train projects and penalty exposure |
| **Risk copilot** | Chat agent that calls tools: supplier data, live news search, impact tracing, alternative sources |
| **Live due diligence** | Deep research on any real company. The agent searches, plans follow-up queries to close gaps, and writes a cited risk report |

## How it works

```
data/ (suppliers, BOM, projects, alternatives, country risk)
   │
   ├── core/model.py      explainable scoring + networkx supply graph + impact propagation
   ├── core/agent.py      tool-calling agent loop with visible reasoning trace
   ├── core/workflows.py  news scan · scenario mapping · mitigation · due diligence
   └── core/llm.py        Nemotron on Nebius Token Factory (OpenAI-compatible) + Tavily search
                          (core/llm_claude.py: optional Claude backend via LLM_PROVIDER=claude)
app.py                    Streamlit UI
```

**Risk score** = weighted sum of factor scores (0–100, higher = riskier):

| Factor | Weight | Source |
|---|---|---|
| External events | 30% | Agent: live news → structured events (type, severity, confidence, relevance, URL) |
| Single-source dependency | 15% | BOM share and lead time |
| Financial health | 15% | Supplier data |
| Country / geopolitical | 10% | Country risk table |
| On-time delivery trend | 10% | Last 6 months |
| Quality | 10% | PPM and non-conformance reports |
| Certification | 10% | Expired, expiring or missing rail certificates |

Bands: low < 40 ≤ watch < 60 ≤ act now.

**Impact propagation:** outage weeks plus a restart ramp (scaled by lead time), minus stock buffer. A second source covers part of the gap for dual-sourced parts. Delay beyond each project's schedule slack is multiplied by its contract penalty per day.

## Run it

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env   # add NEBIUS_API_KEY and TAVILY_API_KEY
.venv/bin/streamlit run app.py
```

`cache/events.json` ships with a pre-run scan so the dashboard is populated without keys. Regenerate the dataset with `python data/seed.py`.

## Data

Supplier and customer names are **fictional**, and so are the planted KPIs. Train product names are used for context only. News signals come from live web search (Tavily). Country risk values are illustrative approximations of public governance indices. To use real data, replace the files in `data/` with ERP/SRM exports in the same shape.
