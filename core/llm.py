"""Nemotron on Nebius Token Factory (OpenAI-compatible) + Tavily search."""
import json
import os
import re
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


MODEL = {"name": None}


def model() -> str:
    if PROVIDER == "claude":
        from core import llm_claude
        return llm_claude.MODEL
    if not MODEL["name"]:
        MODEL["name"] = default_model()
    return MODEL["name"]


THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def clean(text: str | None) -> str:
    text = THINK_RE.sub("", text or "")
    return text.split("</think>")[-1].strip()


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
    return client().chat.completions.create(**kwargs).choices[0].message


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
