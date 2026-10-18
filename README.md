# RailRisk Radar

Supplier selection and risk intelligence for rail procurement. Built for the **Siemens: Supplier Risk Intelligence** challenge at Nebius Build Week (Berlin, 18 Oct 2026).

A train is built from tens of thousands of parts. A buyer sourcing a critical component has to narrow hundreds of candidate suppliers down to a shortlist, compare them side by side and justify the final choice. RailRisk Radar does that over the challenge's 10,000-supplier dataset, answers questions in plain language grounded in the data, and researches any real company on the web.

## What it does

| Tab | What happens |
|---|---|
| **Find suppliers** | Filter 10,000 suppliers by TRI, level, sourcing risk, complexity, delivery and confirmation rates, PO volume, and knock-out rules ("no Critical financial health"). Rank by the official TRI or a **risk lens**, then tick rows to shortlist them |
| **Compare shortlist** | Up to 20 suppliers side by side: ranking table, 18-score heatmap, TRI composition by risk family, radar overlay and a head-to-head diff. **Write decision memo** drafts a cited selection memo from the comparison data (download as .md) |
| **Supplier profile** | Exact explanation of any supplier's TRI (waterfall from the dataset average), percentile per score, operational metrics, and lower-risk alternatives with a similar profile |
| **Ask the data** | Chat assistant that calls tools over the dataset (filter, compare, explain, statistics). It picks its own charts to show under the answer and can add suppliers to the shortlist. The full tool trace is visible |
| **Research agent** | Name a real company. The agent plans its research, searches news and the web, reads the company's own site, **digs deeper on red flags**, closes evidence gaps, then scores the company on the dataset's 18 dimensions with a source link behind each finding. It computes a TRI with the dataset's formula, so you can see where a real company would rank among your 10,000 suppliers |
| **Rail impact lab (demo data)** | Extension on a separate, fictional 32-supplier rail network: supplier → component → train project → € penalty cascade, live news scan, what-if disruption simulation, rail copilot. Suppliers here carry their own **exposure score** (act now ≥ 60, watch 40–59, low < 40), a different scale from the dataset TRI |

## What we found in the data

- **Total_Risk_Index is an exact weighted sum** of the 18 scores. We recovered the weights by regression and verified them on all 10,000 rows: Operational Resilience, Financial Health and Quality 10% each; Compliance 8%; Credit Rating, Safety and Sub-Tier Visibility 6% each; Geopolitical, Governance and ESG 5% each; Environmental, Labor, Digital Security, Political Stability and Industry Benchmark 4% each; Market, Media and External Intelligence 3% each. Every "why is this TRI high?" answer is therefore exact, not a guess.
- Levels: Low < 25 ≤ Medium < 50 ≤ High < 75 ≤ Critical.
- The operational metrics are not part of the TRI. Delivery rating still correlates strongly with it (r = −0.71), which suggests the scores predict real delivery problems.
- Hard-to-replace suppliers (Sourcing Risk High) average TRI 61, versus 39 for easy-to-replace ones.
- The dataset has no country, category or component columns, so the assistant says so instead of guessing.

**Risk lenses** re-weight the same 18 scores for a sourcing situation: *Safety-critical component*, *Long-term strategic partner*, *ESG & compliance first*, or *Custom* sliders. The official TRI stays visible everywhere.

## How it works

```
supplier_risk_dataset.csv, risk_criteria_description.md   (challenge inputs)
   │
   ├── core/dataset.py    loading, exact TRI decomposition, filters, comparison, lenses, swap candidates
   ├── core/agent.py      tool-calling agent loop with visible trace; dataset tools + rail tools
   ├── core/workflows.py  research agent · decision memo · rail news scan, scenarios, mitigation
   ├── core/llm.py        Nemotron on Nebius Token Factory (OpenAI-compatible) + Tavily search/extract
   │                      (core/llm_claude.py: optional Claude backend via LLM_PROVIDER=claude)
   └── core/model.py      rail extension: scoring + networkx supply graph + impact propagation (data/)
views/                    one module per tab; charts.py holds the Plotly figures
app.py                    Streamlit shell: login, sidebar (lens, shortlist), tabs
```

## Run it

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env   # add NEBIUS_API_KEY and TAVILY_API_KEY; optional APP_USERS=jury:password
.venv/bin/streamlit run app.py
```

Filtering, comparison and profiles work without any keys. The chat assistant, memo and research agent need an LLM key, and the research agent also needs Tavily. `python prewarm.py` pre-runs the slow agent workflows into `cache/` so every tab opens populated.

## Deploy

Every new session opens with the demo results tracked in `cache/demo/` (research report, memo, threats, scenario, response plan). Results a user produces stay in that user's session, and so does the model picked in the sidebar, so jurors don't overwrite each other. `python prewarm.py` regenerates the seeds; `python prewarm.py --local` writes gitignored `cache/last_*.json` instead, which take precedence on that machine. Set `PERSIST_DEMO_CACHE=1` locally to save each new result there too. Leave it unset on a shared deployment.

**Login.** `APP_USERS="jury:password,alice:other"` turns on a sign-in form. Without it the app is open.

**Streamlit Community Cloud.** Point the app at `app.py` and paste the keys under *App settings → Secrets*, using [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example) as the template (`APP_USERS`, `NEBIUS_API_KEY`, `TAVILY_API_KEY`). `app.py` copies these secrets into the environment unless the variable is already set there.

**Docker.**

```bash
docker build -t railrisk-radar .
docker run --rm -p 8501:8501 --env-file .env railrisk-radar   # honours $PORT if the platform sets it
```

`.env`, `.streamlit/secrets.toml`, `.venv` and `.git` are kept out of the image by `.dockerignore`. Pass keys at runtime.

## Data

The 10,000 suppliers are the challenge's anonymized dataset. The rail impact lab uses separate fictional suppliers, customers and KPIs (`data/`, regenerate with `python data/seed.py`); train product names are used for context only. News and research come from live web search.
