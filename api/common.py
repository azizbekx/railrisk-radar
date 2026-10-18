"""Shared API helpers: JSON-safe conversion, NDJSON streaming of agent logs, lens weights, supplier rows."""
import json
import math
import queue
import threading

import numpy as np
import pandas as pd
from fastapi.responses import StreamingResponse

from core import agent, dataset as ds
from core.fmt import summarize


# keep proxies (Render, nginx) from buffering the stream so agent steps appear live
NO_BUFFER = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def jsonable(o):
    """Recursively convert numpy/pandas values so json.dumps never falls back to strings."""
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [jsonable(v) for v in o]
    if isinstance(o, pd.DataFrame):
        return jsonable(o.to_dict(orient="records"))
    if isinstance(o, pd.Series):
        return jsonable(o.to_dict())
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def _line(event: str, data) -> str:
    if event == "step" and isinstance(data, dict) and data.get("type") == "tool_result":
        data = {**data, "summary": summarize(data.get("name", ""), data.get("content"))}
    return json.dumps({"event": event, "data": jsonable(data)}, default=str) + "\n"


def stream(fn, *args, **kwargs) -> StreamingResponse:
    """Run fn(*args, log=..., **kwargs) in a thread. Streams NDJSON lines:
    {"event": "step", "data": <log item>} ... then {"event": "result", "data": <return value>}
    or {"event": "error", "data": "<message>"}."""
    q: queue.Queue = queue.Queue()

    def target():
        try:
            q.put(_line("result", fn(*args, log=lambda s: q.put(_line("step", s)), **kwargs)))
        except Exception as e:  # surfaced to the UI, not swallowed
            q.put(_line("error", str(e)))
        q.put(None)

    threading.Thread(target=target, daemon=True).start()

    def gen():
        while (m := q.get()) is not None:
            yield m

    return StreamingResponse(gen(), media_type="application/x-ndjson", headers=NO_BUFFER)


def stream_steps(steps) -> StreamingResponse:
    """Stream a generator of step dicts (e.g. core.agent.run) as {"event": "step"} lines, then {"event": "done"}."""
    def gen():
        try:
            for s in steps:
                yield _line("step", s)
        except Exception as e:
            yield _line("error", str(e))
        yield _line("done", None)

    return StreamingResponse(gen(), media_type="application/x-ndjson", headers=NO_BUFFER)


def lens_weights(weights: dict | None) -> dict:
    """Buyer lens weights from the request; falls back to the official TRI weights."""
    return ds.normalize_weights(weights) if weights else ds.TRI_WEIGHTS


def row(sid: str, weights: dict | None = None) -> dict:
    """Compact supplier row used by tables, the shortlist and pickers."""
    r = ds.df().loc[sid]
    out = {"id": sid, "name": r["Supplier Name"], "tri": int(r["Total_Risk_Index"]), "level": r["Total_Risk_Index_Level"],
           "tri_percentile": float(r["TRI_Percentile"]), "sourcing": r["Sourcing Risk Level"],
           "complexity": r["Supply Chain Complexity"], "delivery": float(r["Supplier Delivery Rating"]),
           "confirmation": float(r["Order Confirmation Rate"]), "change": float(r["Order Change Rate"]),
           "po": float(r[ds.PO])}
    if weights:
        w = lens_weights(weights)
        out["lens_index"] = round(sum(float(r[c]) * v for c, v in w.items()), 1)
    return out


def last(key: str):
    """Last result: local cache/last_<key>.json, else the tracked seed cache/demo/<key>.json, else None."""
    for f in (agent.CACHE / f"last_{key}.json", agent.CACHE / "demo" / f"{key}.json"):
        if f.exists():
            return json.loads(f.read_text())
    return None


def remember(key: str, value):
    try:
        (agent.CACHE / f"last_{key}.json").write_text(json.dumps(jsonable(value), default=str))
    except OSError:
        pass
