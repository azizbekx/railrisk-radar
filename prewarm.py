"""Pre-run the slow agent workflows so every tab opens populated (and the demo survives a slow API).

Run: .venv/bin/python prewarm.py [--scan] [--local]

By default this regenerates the tracked demo seeds in cache/demo/<key>.json, which a fresh clone or a
deployment loads into each new session. With --local it writes cache/last_<key>.json instead (gitignored,
takes precedence over the seeds on this machine only). Review seeds before committing them.
"""
import json
import sys

from core import agent, dataset as ds, model as m, workflows as wf
from core.fmt import trace_line

SCENARIO = "Severe flooding in Penang, Malaysia shuts semiconductor plants for 5 weeks"
DD_COMPANY = "Knorr-Bremse"
MEMO_IDS = ["SUPP_00609", "SUPP_03267", "SUPP_07260", "SUPP_03469", "SUPP_04741"]
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
order = sorted(MEMO_IDS, key=lambda sid: ds.df().loc[sid, "Total_Risk_Index"])
save("memo", {"text": wf.shortlist_memo(order[0], order, ds.TRI_WEIGHTS, "Dataset TRI (official)"),
              "pick": order[0], "ids": order})
