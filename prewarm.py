"""Pre-run the slow agent workflows so every tab opens populated (and the demo survives a slow API).

Run: .venv/bin/python prewarm.py [--scan]
"""
import json
import sys

from core import agent, model as m, workflows as wf
from core.fmt import trace_line

SCENARIO = "Severe flooding in Penang, Malaysia shuts semiconductor plants for 5 weeks"
DD_COMPANY = "Knorr-Bremse"


def save(key, value):
    (agent.CACHE / f"last_{key}.json").write_text(json.dumps(value, default=str))
    print(f"saved {key}")


if "--scan" in sys.argv:
    wf.scan_many(list(m.suppliers()), workers=8)
    print("scan done")

save("threats", wf.headline_threats())
sc = wf.scenario(SCENARIO)
save("scenario", sc)
trace, answer = [], ""
for step in agent.run(wf.response_prompt(sc), max_steps=8):
    if step["type"] == "answer":
        answer = step["content"]
    else:
        trace.append(trace_line(step))
save("response", {"trace": trace, "answer": answer})
save("dd", wf.due_diligence(DD_COMPANY))
