"""Nemotron on Nebius Token Factory (OpenAI-compatible) + Tavily search."""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# "nebius" (Nemotron on Token Factory, used in production) or "claude" (Anthropic, local dev)
PROVIDER = os.getenv("LLM_PROVIDER", "nebius").lower()
BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
# Preference order when NEMOTRON_MODEL is not set: biggest Nemotron available wins
PREFERRED = ["ultra", "super", "nano-30b", "nemotron"]


@lru_cache
def client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=os.getenv("NEBIUS_API_KEY", "missing"), timeout=120, max_retries=2)


@lru_cache
def available_models() -> list[str]:
    if PROVIDER == "claude":
        return []
    try:
        return sorted(m.id for m in client().models.list().data)
    except Exception:
        return []


def nemotron_models() -> list[str]:
    return [m for m in available_models() if "nemotron" in m.lower()]


def default_model() -> str:
    if os.getenv("NEMOTRON_MODEL"):
        return os.getenv("NEMOTRON_MODEL")
    cands = nemotron_models()
    for key in PREFERRED:
        for m in cands:
            if key in m.lower() and "reward" not in m.lower() and "embed" not in m.lower():
                return m
    return "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"


MODEL = {"name": None}  # process-wide cache of default_model(); the UI choice lives in _SESSION_MODEL
# Per-session model choice. app.py sets it on every run; contextvars keep one user's pick out of other sessions.
_SESSION_MODEL: ContextVar[str | None] = ContextVar("llm_model", default=None)


def set_model(name: str | None):
    _SESSION_MODEL.set(name or None)


def model() -> str:
    if PROVIDER == "claude":
        from core import llm_claude
        return llm_claude.MODEL
    if _SESSION_MODEL.get():
        return _SESSION_MODEL.get()
    if not MODEL["name"]:
        MODEL["name"] = default_model()
    return MODEL["name"]


class ContextPool(ThreadPoolExecutor):
    """ThreadPoolExecutor whose workers inherit the caller's context (and so the session's model)."""

    def submit(self, fn, /, *args, **kwargs):
        return super().submit(copy_context().run, fn, *args, **kwargs)


THINK_RE = re.compile(r"<think>.*?</think>", re.S)
SPECIAL_RE = re.compile(r"<\|[a-z_]+\|>|</?(?:tool_call|tool_response|function_calls?)>|<TOOLCALL>|</TOOLCALL>")


def clean(text: str | None) -> str:
    text = THINK_RE.sub("", text or "")
    text = text.split("</think>")[-1]
    if "<think>" in text:  # reasoning that never closed: whatever follows it is not the answer
        text = text.split("<think>")[0]
    # "![compare_bars]" / "![chart](https://example.com/..)" placeholders for charts the app renders itself
    text = re.sub(r"!\[[^\]]*\](?!\()|!\[[^\]]*\]\((?:https?://)?(?:www\.)?example\.[^)]*\)", "", text)
    return SPECIAL_RE.sub("", text).strip()


# ---------- tool calls emitted as text ----------
# Nemotron sometimes writes the call into `content` instead of structured tool_calls, as
# <tool_call>{"name": .., "arguments": {..}}</tool_call>, <TOOLCALL>[{..}]</TOOLCALL>, the XML form
# <function=name><parameter=key>value</parameter></function>, or a bare/fenced {"name":..,"arguments":..}.

TAGGED_RE = re.compile(r"<(tool_call|TOOLCALL)>(.*?)(?:</\1>|$)", re.S)
XML_FN_RE = re.compile(r"<function=([\w.\-]+)>(.*?)(?:</function>|$)", re.S)
XML_PARAM_RE = re.compile(r"<parameter=([\w\-]+)>\s*(.*?)\s*(?:</parameter>|(?=<parameter=)|$)", re.S)


def _json_calls(blob: str) -> list[dict]:
    blob = blob.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)```", blob, re.S)
    blob = fence.group(1).strip() if fence else blob
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return []
    out = []
    for c in data if isinstance(data, list) else [data]:
        if not isinstance(c, dict):
            continue
        c = c.get("function", c) if isinstance(c.get("function"), dict) else c
        name = c.get("name") or c.get("tool") or c.get("function")
        args = c.get("arguments", c.get("parameters", c.get("args", {})))
        if isinstance(name, str):
            out.append({"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)})
    return out


def _xml_value(v: str):
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def parse_text_tool_calls(text: str, names: set[str]) -> tuple[list[dict], str]:
    """Tool calls written into a reply's text -> ([{name, arguments}], text without them).
    Only calls to known tool names count, so prose that merely mentions JSON is left alone."""
    if not text:
        return [], text or ""
    calls, rest = [], text
    for m in TAGGED_RE.finditer(text):
        found = _json_calls(m.group(2)) or [
            {"name": fm.group(1), "arguments": json.dumps({k: _xml_value(v) for k, v in XML_PARAM_RE.findall(fm.group(2))})}
            for fm in XML_FN_RE.finditer(m.group(2))]
        calls += found
        if found:
            rest = rest.replace(m.group(0), "")
    if not calls:
        for fm in XML_FN_RE.finditer(text):
            calls.append({"name": fm.group(1),
                          "arguments": json.dumps({k: _xml_value(v) for k, v in XML_PARAM_RE.findall(fm.group(2))})})
            rest = rest.replace(fm.group(0), "")
    if not calls:
        stripped = THINK_RE.sub("", text).strip()
        cand = re.fullmatch(r"(?:```(?:json)?\s*)?([\[{].*[\]}])\s*(?:```)?", stripped, re.S)
        if cand and '"name"' in cand.group(1):
            calls = _json_calls(cand.group(1))
            rest = "" if calls else rest
    for c in calls:
        c["name"] = c["name"].split(".")[-1].strip()  # "functions.explain_risk" -> "explain_risk"
    calls = [c for c in calls if c["name"] in names]
    return calls, (rest if calls else text)


class _Fn:
    def __init__(self, name, arguments):
        self.name, self.arguments = name, arguments


class _Call:
    def __init__(self, i, name, arguments):
        self.id, self.type, self.function = f"text_call_{i}", "function", _Fn(name, arguments)


class _Reply:
    def __init__(self, content, tool_calls, reasoning_content=None):
        self.content, self.tool_calls, self.reasoning_content = content, tool_calls, reasoning_content


def chat(messages: list[dict], tools: list | None = None, temperature: float = 0.2, max_tokens: int = 2500):
    if PROVIDER == "claude":
        from core import llm_claude
        return llm_claude.chat(messages, tools=tools, max_tokens=max_tokens)
    # drop provider-private keys such as _claude_content
    messages = [{k: v for k, v in msg.items() if not k.startswith("_")} for msg in messages]
    kwargs = {"model": model(), "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    msg = client().chat.completions.create(**kwargs).choices[0].message
    if tools and not msg.tool_calls and msg.content:
        names = {t["function"]["name"] for t in tools}
        calls, rest = parse_text_tool_calls(msg.content, names)
        if calls:
            return _Reply(rest.strip(), [_Call(i, c["name"], c["arguments"]) for i, c in enumerate(calls)],
                          getattr(msg, "reasoning_content", None))
    return msg


def extract_json(text: str):
    """Parse the first JSON object/array in a model reply."""
    text = clean(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no JSON in reply: {text[:300]}")


def ask_json(system: str, user: str, retries: int = 2, max_tokens: int = 3000):
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last = None
    for _ in range(retries + 1):
        reply = chat(msgs, temperature=0.1, max_tokens=max_tokens)
        try:
            return extract_json(reply.content)
        except ValueError as e:
            last = e
            msgs += [{"role": "assistant", "content": reply.content or ""},
                     {"role": "user", "content": "Reply with valid JSON only, no prose."}]
    raise last


# ---------- Tavily ----------

@lru_cache
def tavily():
    from tavily import TavilyClient
    return TavilyClient(api_key=os.getenv("TAVILY_API_KEY", ""))


def search_news(query: str, days: int = 60, max_results: int = 5) -> list[dict]:
    res = tavily().search(query=query, topic="news", days=days, max_results=max_results)
    return [{"title": r.get("title"), "url": r.get("url"), "date": r.get("published_date", ""),
             "content": (r.get("content") or "")[:700]} for r in res.get("results", [])]


def search_web(query: str, max_results: int = 5) -> list[dict]:
    res = tavily().search(query=query, search_depth="advanced", max_results=max_results)
    return [{"title": r.get("title"), "url": r.get("url"), "content": (r.get("content") or "")[:900]}
            for r in res.get("results", [])]


def keys_status() -> dict:
    llm_key = os.getenv("ANTHROPIC_API_KEY") if PROVIDER == "claude" else os.getenv("NEBIUS_API_KEY")
    return {"llm": bool(llm_key), "provider": PROVIDER, "tavily": bool(os.getenv("TAVILY_API_KEY"))}
