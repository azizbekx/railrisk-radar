"""Run the data chat assistant (core.agent.run with DATA_TOOLS/DATA_SYSTEM, as views/chat.py does) against
Nemotron on Nebius Token Factory and score it with checks computed from core.dataset.

    .venv/bin/python -m evals.chat_evals                       # default model, all cases
    .venv/bin/python -m evals.chat_evals --model all           # every Nemotron chat model
    .venv/bin/python -m evals.chat_evals --case jury --repeat 3
    .venv/bin/python -m evals.chat_evals --model nvidia/nemotron-3-super-120b-a12b --case typo_id -v

Each LLM call costs Token Factory credits; the run prints the total number of calls.
JSON results land in evals/results/ (gitignored)."""
import argparse
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from core import agent, dataset as ds, llm
from evals.cases import CASES, Run, generic

RESULTS = Path(__file__).resolve().parent / "results"
MAX_STEPS = 8          # agent.run default, which views/chat.py uses
_tls = threading.local()
_orig_chat = llm.chat


def _logged_chat(messages, tools=None, **kw):
    """Wraps llm.chat to count calls and keep the raw replies for diagnosis."""
    t = time.time()
    rec = getattr(_tls, "rec", None)
    try:
        msg = _orig_chat(messages, tools=tools, **kw)
    except Exception as e:
        if rec is not None:
            rec["llm"].append({"error": str(e)[:500], "secs": round(time.time() - t, 2)})
        raise
    if rec is not None:
        rec["llm"].append({
            "secs": round(time.time() - t, 2), "with_tools": bool(tools),
            "content": (msg.content or "")[:3000],
            "reasoning_chars": len(getattr(msg, "reasoning_content", None) or ""),
            "tool_calls": [{"name": c.function.name, "arguments": (c.function.arguments or "")[:1500]}
                           for c in (msg.tool_calls or [])]})
    return msg


def use_model(name: str):
    """Point llm.chat at a model without touching how the app stores its selection."""
    llm.model = lambda: name
    if isinstance(getattr(llm, "MODEL", None), dict):
        llm.MODEL["name"] = name


def chat_models() -> list[str]:
    return [m for m in llm.nemotron_models() if not any(k in m.lower() for k in ("reward", "embed", "guard"))]


def run_case(case, model: str) -> dict:
    rec = {"case": case.name, "model": model, "prompt": case.prompt(), "llm": [], "steps": []}
    _tls.rec = rec
    t = time.time()
    try:
        for step in agent.run(case.prompt(), [], tools=agent.DATA_TOOLS, system=agent.DATA_SYSTEM):
            rec["steps"].append(step)
    except Exception as e:  # the agent itself should never raise
        rec["steps"].append({"type": "error", "content": f"agent raised: {e!r}"})
    finally:
        _tls.rec = None
    rec["latency"] = round(time.time() - t, 1)
    rec["llm_calls"] = len(rec["llm"])
    return score(rec, case)


def score(rec: dict, case) -> dict:
    answers = [s["content"] for s in rec["steps"] if s["type"] == "answer"]
    rec["answer"] = answers[-1] if answers else ""
    r = Run(rec["answer"], rec["steps"])
    rec["tool_calls"] = [{"name": n, "args": a} for n, a, _ in r.calls]
    try:
        checks = generic(r, rec, MAX_STEPS) + case.checks(r)
    except Exception as e:
        checks = [("checks_crashed", False, repr(e))]
    rec["checks"] = [{"check": n, "ok": ok, "detail": d} for n, ok, d in checks]
    rec["passed"] = all(ok for _, ok, _ in checks)
    return rec


def short(model: str) -> str:
    return model.split("/")[-1]


def report(recs: list[dict], models: list[str]):
    names = list(dict.fromkeys(r["case"] for r in recs))
    w = max(len(n) for n in names) + 2
    cols = [short(m)[:26] for m in models]
    print("\n" + "case".ljust(w) + " | ".join(c.ljust(26) for c in cols))
    for n in names:
        cells = []
        for m in models:
            rs = [r for r in recs if r["case"] == n and r["model"] == m]
            if not rs:
                cells.append("-".ljust(26))
                continue
            ok = sum(r["passed"] for r in rs)
            lat = statistics.median(r["latency"] for r in rs)
            calls = statistics.mean(r["llm_calls"] for r in rs)
            cells.append(f"{'PASS' if ok == len(rs) else 'FAIL'} {ok}/{len(rs)} {lat:5.1f}s {calls:.1f}c".ljust(26))
        print(n.ljust(w) + " | ".join(cells))
    print()
    for m in models:
        rs = [r for r in recs if r["model"] == m]
        if not rs:
            continue
        lats = [r["latency"] for r in rs]
        print(f"{short(m)}: {sum(r['passed'] for r in rs)}/{len(rs)} passed, latency median {statistics.median(lats):.1f}s "
              f"max {max(lats):.1f}s, {sum(r['llm_calls'] for r in rs)} LLM calls")
        for r in rs:
            fails = [f"{c['check']}({c['detail'][:140]})" if c["detail"] else c["check"] for c in r["checks"] if not c["ok"]]
            if fails:
                print(f"   x {r['case']}: " + "; ".join(fails))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", action="append", help="model id, 'default' or 'all' (repeatable)")
    ap.add_argument("--case", action="append", help="case name or substring (repeatable)")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4, help="cases run in parallel per model")
    ap.add_argument("--tag", default="", help="label stored in the results file name")
    ap.add_argument("-v", "--verbose", action="store_true", help="print answers and tool calls")
    ap.add_argument("--list", action="store_true", help="list cases and models, then exit")
    ap.add_argument("--rescore", nargs="+", metavar="JSON", help="re-apply the checks to saved results (no LLM calls)")
    a = ap.parse_args()

    if a.rescore:
        by_name = {c.name: c for c in CASES}
        recs = [score(r, by_name[r["case"]]) for f in a.rescore for r in json.loads(Path(f).read_text())
                if r["case"] in by_name and (not a.case or any(k in r["case"] for k in a.case))]
        report(recs, list(dict.fromkeys(r["model"] for r in recs)))
        return
    if a.list:
        print("cases:", ", ".join(c.name for c in CASES))
        print("models:", ", ".join(chat_models()), "| default:", llm.default_model())
        return
    models = []
    for m in a.model or ["default"]:
        models += chat_models() if m == "all" else [llm.default_model()] if m == "default" else [m]
    models = list(dict.fromkeys(models))
    cases = [c for c in CASES if not a.case or any(k == c.name or k in c.name for k in a.case)]
    if not cases:
        raise SystemExit(f"no case matches {a.case}")
    ds.df(), ds.means()  # warm caches before threads
    llm.chat = _logged_chat

    recs = []
    for model in models:
        use_model(model)
        jobs = [c for c in cases for _ in range(a.repeat)]
        print(f"== {model}: {len(jobs)} runs", flush=True)
        with ThreadPoolExecutor(max(1, a.jobs)) as ex:
            for rec in ex.map(lambda c: run_case(c, model), jobs):
                recs.append(rec)
                print(f"  {'PASS' if rec['passed'] else 'FAIL'} {rec['case']:<26} {rec['latency']:5.1f}s "
                      f"{rec['llm_calls']} calls  tools={[t['name'] for t in rec['tool_calls']]}", flush=True)
                if a.verbose:
                    print("     args:", json.dumps([t["args"] for t in rec["tool_calls"]], default=str)[:600])
                    print("     answer:", rec["answer"][:1500].replace("\n", "\n             "))
    llm.chat = _orig_chat

    report(recs, models)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}{'-' + a.tag if a.tag else ''}.json"
    out.write_text(json.dumps(recs, indent=1, default=str))
    print(f"\n{sum(r['llm_calls'] for r in recs)} LLM calls total. Results: {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")


if __name__ == "__main__":
    main()
