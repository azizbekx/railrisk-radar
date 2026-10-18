"""Pre-run the slow agent workflows so every tab opens populated (and the demo survives a slow API).

Run: .venv/bin/python prewarm.py [--scan] [--team | --research] [--local]   (--team / --research: only that run)

By default this regenerates the tracked demo seeds in cache/demo/<key>.json, which a fresh clone or a
deployment loads into each new session. With --local it writes cache/last_<key>.json instead (gitignored,
takes precedence over the seeds on this machine only). Review seeds before committing them.
"""
import json
import sys

from core import agent, dataset as ds, model as m, team, workflows as wf
from core.fmt import trace_line

SCENARIO = "Severe flooding in Penang, Malaysia shuts semiconductor plants for 5 weeks"
DD_COMPANY = "Knorr-Bremse"
TEAM_IDS = ["SUPP_00012", "SUPP_00450", "SUPP_00731", "SUPP_00018"]  # the Compare tab's jury example
TEAM_CONTEXT = "Brake control units for a regional train: safety-critical, 5-year frame contract"
LOCAL = "--local" in sys.argv
OUT = agent.CACHE if LOCAL else agent.CACHE / "demo"


def save(key, value):
    OUT.mkdir(exist_ok=True)
    f = OUT / (f"last_{key}.json" if LOCAL else f"{key}.json")
    f.write_text(json.dumps(value, default=str))
    print(f"saved {f.relative_to(agent.CACHE.parent)}")


if "--scan" in sys.argv:
    wf.scan_many(list(m.suppliers()), workers=8)
    print("scan done")

if "--research" not in sys.argv:
    save("team", team.run(TEAM_IDS, TEAM_CONTEXT, "Dataset TRI (official)", ds.TRI_WEIGHTS))
if "--team" in sys.argv:
    sys.exit()

if "--research" not in sys.argv:
    save("threats", wf.headline_threats())
    sc = wf.scenario(SCENARIO)
    save("scenario", sc)
    trace, answer = [], ""
    for step in agent.run(wf.response_prompt(sc), max_steps=8, tools=agent.RAIL_TOOLS):
        if step["type"] == "answer":
            answer = step["content"]
        else:
            trace.append(trace_line(step))
    save("response", {"trace": trace, "answer": answer})

# same shape as api/routes/research.py: raw steps (the React trace renders them) and the downloadable markdown
steps = []
rep = wf.research_company(DD_COMPANY, log=steps.append)
rep["trace"] = steps
rep["markdown"] = wf.report_markdown(rep)
save("research", rep)
