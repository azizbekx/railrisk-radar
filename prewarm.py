"""Pre-run the slow agent workflows so every tab opens populated (and the demo survives a slow API).

Run: .venv/bin/python prewarm.py [--scan] [--team]   (--team: only the Compare tab's agent team run)
"""
import json
import sys

from core import agent, dataset as ds, model as m, team, workflows as wf
from core.fmt import trace_line

SCENARIO = "Severe flooding in Penang, Malaysia shuts semiconductor plants for 5 weeks"
DD_COMPANY = "Knorr-Bremse"
TEAM_IDS = ["SUPP_00012", "SUPP_00450", "SUPP_00731", "SUPP_00018"]  # the Compare tab's jury example
TEAM_CONTEXT = "Brake control units for a regional train: safety-critical, 5-year frame contract"


def save(key, value):
    (agent.CACHE / f"last_{key}.json").write_text(json.dumps(value, default=str))
    print(f"saved {key}")


if "--scan" in sys.argv:
    wf.scan_many(list(m.suppliers()), workers=8)
    print("scan done")

save("team", team.run(TEAM_IDS, TEAM_CONTEXT, "Dataset TRI (official)", ds.TRI_WEIGHTS))
if "--team" in sys.argv:
    sys.exit()

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
trace = []
rep = wf.research_company(DD_COMPANY, log=lambda s: trace.append(trace_line(s)))
rep["trace"] = trace
save("research", rep)
