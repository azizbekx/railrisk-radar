"""research page API. Owned by the research slice."""
from fastapi import APIRouter
from pydantic import BaseModel

from api.common import jsonable, last, remember, stream
from core import workflows as wf

router = APIRouter()


class ResearchIn(BaseModel):
    company: str


def _run(company: str, log=None):
    """Runs the research agent, capturing every log step as the report's trace, then caches the result."""
    steps: list = []

    def capture(step):
        steps.append(step)
        if log:
            log(step)

    rep = wf.research_company(company, log=capture)
    rep["trace"] = steps
    rep["markdown"] = wf.report_markdown(rep)
    remember("research", rep)
    return rep


@router.post("/research")
def research(body: ResearchIn):
    """Streams NDJSON agent steps, then a final {"event": "result", "data": <report>}."""
    return stream(_run, body.company)


@router.get("/research/last")
def research_last():
    """Cached last report (cache/last_research.json) or null. Older caches lack the markdown, so build it for the download."""
    rep = last("research")
    if rep and not rep.get("markdown"):
        try:
            rep["markdown"] = wf.report_markdown(rep)
        except (KeyError, TypeError):
            pass
    return jsonable(rep)
