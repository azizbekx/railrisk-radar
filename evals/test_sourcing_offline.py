"""Offline checks of the sourcing agent (Find suppliers): funnel, offers and the fallbacks when agents misbehave.
No LLM calls, no credits.

    .venv/bin/python -m evals.test_sourcing_offline"""
import json

from core import dataset as ds, llm, sourcing
from evals.test_agent_offline import reply


def with_fakes(chat, news=None):
    def wrap(fn):
        def run():
            orig_chat, orig_news = llm.chat, llm.search_news
            llm.chat = chat
            llm.search_news = news or (lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no key")))
            try:
                fn()
            finally:
                llm.chat, llm.search_news = orig_chat, orig_news
        run.__name__ = fn.__name__
        return run
    return wrap


def failing_chat(messages, **kw):
    raise RuntimeError("LLM down")


def test_offers_deterministic():
    w = ds.normalize_weights(ds.LENSES["Safety-critical component"])
    a, funnel, risk = sourcing.screen("brake_control_unit", w)
    b, _, _ = sourcing.screen("brake_control_unit", w)
    assert a == b and len(a) == sourcing.LONGLIST
    counts = [f["count"] for f in funnel]
    assert counts == sorted(counts, reverse=True), counts
    assert all(ds.part_gate(ds.df().loc[a], "safety_critical"))
    assert all(all(sourcing.certs_held(i, "brake_control_unit").values()) for i in a)
    assert sourcing.offer(a[0], "brake_control_unit") == sourcing.offer(a[0], "brake_control_unit")
    rows = sourcing.score_offers(a, "brake_control_unit", risk, sourcing.brief_of("brake_control_unit", 10, 20, None, ""))
    late = [r["late"] for r in rows]
    assert late == sorted(late), "late offers must rank after on-time ones"
    assert all(0 <= r["score"] <= 100 for r in rows)


def test_weights_sum_to_one():
    for p in ds.PART_TYPES:
        assert abs(sum(sourcing.weights(p).values()) - 1) < 1e-6, p


def test_fallback_parse():
    p = sourcing._fallback_parse("I need 400 brake units within 6 months, target €17k each")
    assert p == {"component": "brake_control_unit", "quantity": 400, "need_by_weeks": 26, "target_unit_price": 17000.0, "notes": ""}
    assert sourcing._fallback_parse("2,000 seat covers in 8 weeks")["component"] == "seat_cover"  # longest alias wins over "seat"


@with_fakes(failing_chat)
def test_run_without_llm_or_news():
    res = sourcing.run("hvac_unit", 48, 20)
    assert len(res["finalists"]) == sourcing.FINALISTS and len(res["top"]) == sourcing.TOP
    assert res["finalists"] == [r["id"] for r in res["longlist"][:sourcing.FINALISTS]]  # score order kept
    order = sorted(res["finalists"], key=lambda i: res["final_score"][i])
    assert [t["id"] for t in res["top"]] == order[:sourcing.TOP]
    assert res["market"]["signals"] == []
    assert len(res["not_chosen"]) == sourcing.FINALISTS - sourcing.TOP
    assert "Sourcing recommendation" in res["memo"]


def scripted_chat():
    """Agents that hallucinate IDs, repeat themselves and cite unknown sources: the run must keep only valid output."""
    def fake(messages, **kw):
        sys = messages[0]["content"]
        user = messages[-1]["content"]
        if "offer analyst" in sys:
            cands = [c["id"] for c in json.loads(user)["candidates"]]
            return reply(json.dumps({"finalists": ["SUPP_99999", cands[11], cands[11], *cands[:3]],
                                     "reasons": {cands[11]: "short lead time"}, "summary": "ok"}))
        if "market intelligence" in sys:
            return reply(json.dumps({"summary": "tight", "signals": [{"title": "x", "source": 1, "severity": "4"},
                                                                     {"title": "bad", "source": 99}], "advice": "strong finances"}))
        if "pick the final" in sys:
            fins = [f["id"] for f in json.loads(user)["finalists"]]
            return reply(json.dumps({"top": [{"id": fins[-1], "role": "Lowest risk"}, {"id": "SUPP_99999"}], "summary": "s"}))
        return reply(json.dumps({"best": "SUPP_99999", "verdict": "v", "red_flags": [{"supplier": "SUPP_99999", "issue": "x"}]}))
    return fake


@with_fakes(scripted_chat(), news=lambda q, **k: [{"title": "t", "url": f"https://news.example/{q[:5]}", "date": "", "content": "c"}])
def test_run_with_messy_agents():
    res = sourcing.run("brake_control_unit", 400, 30)
    cands = [r["id"] for r in res["longlist"][:sourcing.CANDIDATES]]
    assert res["finalists"][0] == cands[11] and len(set(res["finalists"])) == sourcing.FINALISTS
    assert set(res["finalists"]) <= set(cands)
    top = [t["id"] for t in res["top"]]
    assert top[0] == sorted(res["finalists"], key=lambda i: res["final_score"][i])[-1]  # leader's pick kept first
    assert len(top) == sourcing.TOP and set(top) <= set(res["finalists"])
    assert len(res["market"]["signals"]) == 1 and res["market"]["signals"][0]["severity"] == 4
    assert all(not t["red_flags"] for t in res["top"])  # flags on unknown IDs dropped


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
