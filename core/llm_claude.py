"""Claude backend (Anthropic SDK) used for local development (production runs on Nebius).

Takes the same OpenAI-style messages/tools the agent builds and returns an object with
.content / .tool_calls / .claude_content, so the rest of the app does not change.
"""
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache

import anthropic

MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")


@lru_cache
def client() -> anthropic.Anthropic:
    return anthropic.Anthropic(timeout=180, max_retries=2)


@dataclass
class _Fn:
    name: str
    arguments: str


@dataclass
class _Call:
    id: str
    function: _Fn
    type: str = "function"


@dataclass
class Reply:
    content: str
    tool_calls: list = field(default_factory=list)
    claude_content: list | None = None  # raw blocks, replayed unchanged (keeps thinking blocks valid)


def _tools(specs: list | None) -> list:
    return [{"name": t["function"]["name"], "description": t["function"]["description"],
             "input_schema": t["function"]["parameters"]} for t in specs or []]


def _messages(messages: list[dict]) -> tuple[str, list]:
    system, out = [], []
    for msg in messages:
        role = msg["role"]
        if role == "system":
            system.append(msg["content"])
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": msg["tool_call_id"], "content": msg["content"]}
            # all results for one assistant turn go back in a single user message
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) \
                    and out[-1]["content"] and out[-1]["content"][0].get("type") == "tool_result":
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        elif role == "assistant" and msg.get("_claude_content") is not None:
            out.append({"role": "assistant", "content": msg["_claude_content"]})
        elif role == "assistant" and msg.get("tool_calls"):
            blocks = [{"type": "text", "text": msg["content"]}] if msg.get("content") else []
            blocks += [{"type": "tool_use", "id": c["id"], "name": c["function"]["name"],
                        "input": json.loads(c["function"]["arguments"] or "{}")} for c in msg["tool_calls"]]
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": role, "content": msg.get("content") or ""})
    return "\n\n".join(system), out


def chat(messages: list[dict], tools: list | None = None, max_tokens: int = 16000) -> Reply:
    system, msgs = _messages(messages)
    kwargs = {"model": MODEL, "max_tokens": max(max_tokens, 16000), "messages": msgs}
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = _tools(tools)
    resp = client().messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        return Reply(content="The model declined this request.")
    text = "".join(b.text for b in resp.content if b.type == "text")
    calls = [_Call(id=b.id, function=_Fn(name=b.name, arguments=json.dumps(b.input)))
             for b in resp.content if b.type == "tool_use"]
    return Reply(content=text, tool_calls=calls, claude_content=resp.content)
