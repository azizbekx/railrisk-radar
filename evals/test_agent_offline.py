"""Offline checks of the agent's robustness to malformed Nemotron output. No LLM calls, no credits.

    .venv/bin/python -m evals.test_agent_offline"""
import json
from types import SimpleNamespace as NS

from core import agent, llm


def reply(content="", calls=()):
    return NS(content=content, reasoning_content=None,
              tool_calls=[NS(id=f"c{i}", type="function", function=NS(name=n, arguments=a)) for i, (n, a) in enumerate(calls)]
              or None)


def scripted(*replies):
    """Fake llm.chat that returns the given replies in order (structured, or raw text parsed like chat() does)."""
    it = iter(replies)
    names = {n for n in agent.DATA_TOOLS}

    def fake(messages, tools=None, **kw):
        r = next(it)
        if isinstance(r, str):  # raw text: run the same text-tool-call parsing as llm.chat
            calls, rest = llm.parse_text_tool_calls(r, names) if tools else ([], r)
            return llm._Reply(rest, [llm._Call(i, c["name"], c["arguments"]) for i, c in enumerate(calls)]) if calls \
                else reply(r)
        return r
    return fake


def run(*replies, q="q"):
    orig = llm.chat
    llm.chat = scripted(*replies)
    try:
        return list(agent.run(q, tools=agent.DATA_TOOLS, system=agent.DATA_SYSTEM))
    finally:
        llm.chat = orig


def results(steps, name):
    return [s["content"] for s in steps if s["type"] == "tool_result" and s["name"] == name]


def answer(steps):
    return next(s["content"] for s in steps if s["type"] == "answer")


def test_args_parsing():
    assert agent.parse_args('{"supplier": "SUPP_00018"}') == {"supplier": "SUPP_00018"}
    assert agent.parse_args(json.dumps('{"supplier": "SUPP_00018"}')) == {"supplier": "SUPP_00018"}  # double-encoded
    assert agent.parse_args("{'supplier': 'SUPP_00018'}") == {"supplier": "SUPP_00018"}
    assert agent.parse_args('{"supplier": "SUPP_00018"} trailing') == {"supplier": "SUPP_00018"}
    assert agent.parse_args("") == {} and agent.parse_args(None) == {} and agent.parse_args("garbage") == {}


def test_coercion():
    c = agent.coerce_args
    ids = ["SUPP_00012", "SUPP_00450", "SUPP_00731"]
    assert c("compare_suppliers", {"suppliers": '["SUPP_00012","SUPP_00450","SUPP_00731"]'})["suppliers"] == ids
    assert c("compare_suppliers", {"suppliers": "SUPP_00012, SUPP_00450 and SUPP_00731"})["suppliers"] == ids
    assert c("get_suppliers", {"supplier": "SUPP_00012"})["suppliers"] == ["SUPP_00012"]
    assert c("get_suppliers", {"supplier_ids": ids})["suppliers"] == ids
    assert c("explain_risk", {"supplier": ["SUPP_00018"]})["supplier"] == "SUPP_00018"
    assert c("compare_suppliers", {"suppliers": ids, "columns": "compliance, cyber"})["columns"] == ["compliance", "cyber"]
    a = c("find_suppliers", {"filters": '[{"field": "Supplier Delivery Rating", "operator": "gt", "value": "97%"}]',
                             "limit": "5", "ascending": "false", "bogus": 1})
    assert a == {"conditions": [{"column": "Supplier Delivery Rating", "op": ">", "value": 97.0}], "limit": 5,
                 "ascending": False}, a
    a = c("find_suppliers", {"conditions": "Sourcing Risk Level == Low, Supplier Delivery Rating > 97"})
    assert a["conditions"] == [{"column": "Sourcing Risk Level", "op": "==", "value": "Low"},
                               {"column": "Supplier Delivery Rating", "op": ">", "value": 97.0}], a
    assert c("find_suppliers", {"conditions": {"column": "TRI", "op": "<", "value": 30}})["conditions"][0]["op"] == "<"


def test_tools_tolerate_bad_input():
    r = agent.run_tool("compare_suppliers", {"suppliers": "SUPP_00012,SUPP_00018",
                                             "columns": ["Compliance_Risk_Level", "Digital_Security_Score"]})
    assert "error" not in r and set(r["columns"]) == {"Compliance_Risk_Score", "Digital_Security_Score"}, r
    assert r["columns"]["Compliance_Risk_Score"]["levels"]["SUPP_00018"] == "Critical"
    assert agent.run_tool("functions.explain_risk", {"supplier": "supp 18"})["total_risk_index"] == 80
    assert "error" in agent.run_tool("explain_risk", {})


def test_fit_keeps_valid_json():
    big = agent.t_get_suppliers([f"SUPP_{i:05d}" for i in range(1, 21)])
    assert len(json.loads(agent._fit(big))["suppliers"]) == 20  # 20 full profiles fit the default budget
    text = agent._fit(big, 12000)
    data = json.loads(text)  # must stay parseable, unlike a blind [:12000] slice
    assert len(text) <= 12000 and data["suppliers"] and "Compliance_Risk_Score_Level" not in data["suppliers"][0]
    assert "truncated" in data


def test_text_tool_calls():
    names = set(agent.DATA_TOOLS)
    p = llm.parse_text_tool_calls
    calls, rest = p('Let me check.\n<tool_call>{"name": "explain_risk", "arguments": {"supplier": "SUPP_00018"}}</tool_call>', names)
    assert calls == [{"name": "explain_risk", "arguments": '{"supplier": "SUPP_00018"}'}] and rest.strip() == "Let me check."
    calls, _ = p("<tool_call>\n<function=get_suppliers>\n<parameter=suppliers>\n[\"SUPP_00012\", \"SUPP_00450\"]\n"
                 "</parameter>\n</function>\n</tool_call>", names)
    assert calls[0]["name"] == "get_suppliers" and json.loads(calls[0]["arguments"]) == {"suppliers": ["SUPP_00012", "SUPP_00450"]}
    calls, _ = p('<TOOLCALL>[{"name": "column_stats", "arguments": {"column": "delivery"}}]</TOOLCALL>', names)
    assert calls[0]["name"] == "column_stats"
    calls, _ = p('```json\n{"name": "explain_risk", "parameters": {"supplier": "SUPP_00018"}}\n```', names)
    assert calls[0]["name"] == "explain_risk"
    assert p('Here is JSON: {"name": "Apex"}', names)[0] == []  # not a tool
    assert llm.clean("<think>plan</think>\n**SUPP_00731**") == "**SUPP_00731**"
    assert llm.clean("<think>never closed") == "" and llm.clean("plan</think>Answer") == "Answer"
    assert llm.clean("See chart.\n\n![compare_bars]") == "See chart." and "![x](http://a)" in llm.clean("![x](http://a)")
    assert llm.clean("Chart:\n![c](https://example.com/charts/x?a=1)") == "Chart:"


def test_loop_text_call_and_empty_final():
    steps = run('<tool_call>{"name": "explain_risk", "arguments": "{\\"supplier\\": \\"SUPP_00018\\"}"}</tool_call>',
                reply(""),                      # empty content after tool use
                reply("**SUPP_00018** has TRI 80."))  # the forced final answer
    assert results(steps, "explain_risk")[0]["total_risk_index"] == 80
    assert answer(steps) == "**SUPP_00018** has TRI 80."


def test_loop_empty_first_reply_retries_with_tools():
    steps = run(reply(""), reply("", [("explain_risk", '{"supplier": "SUPP_00018"}')]), reply("TRI 80, see drivers."))
    assert results(steps, "explain_risk") and answer(steps) == "TRI 80, see drivers."


def test_loop_repeat_guard():
    same = ("get_suppliers", '{"suppliers": ["SUPP_00012"]}')
    steps = run(*[reply("", [same])] * 3, reply("final"))
    assert len(results(steps, "get_suppliers")) == 1 and answer(steps) == "final"


def test_loop_draft_answer_kept():
    draft = "**SUPP_00018** has a Total Risk Index of 80 (Critical). " + "Operational Resilience 95 drives it. " * 6
    steps = run(reply("", [("explain_risk", '{"supplier": "SUPP_00018"}')]),
                reply(draft, [("show_chart", '{"kind": "risk_breakdown", "suppliers": "SUPP_00018"}')]),
                reply("The chart above shows the breakdown."))
    a = answer(steps)
    assert a.startswith("**SUPP_00018**") and "chart above" in a
    assert results(steps, "show_chart")[0]["suppliers"] == ["SUPP_00018"]


def test_loop_max_steps():
    steps = run(*[reply("", [("column_stats", json.dumps({"column": f"c{i}"}))]) for i in range(8)], reply("done"))
    assert answer(steps) == "done"


if __name__ == "__main__":
    tests = [(k, v) for k, v in dict(globals()).items() if k.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"{len(tests)} passed")
