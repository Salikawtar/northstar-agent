"""One door to every AI model call (OpenRouter).

Why one door: every agent, the router and the grader call models the same
way, so cost, retries, the spending limit and the replay cache are handled
once, here, instead of in each module.

Modes (llm_client.mode in settings.yaml):
- auto    : live if OPENROUTER_API_KEY is set, otherwise replay (default)
- live    : call OpenRouter and save every answer to the cache
- replay  : never call the network; answer only from the cache. This is how
            markers re-run our results for free, with no key.

What it protects against:
- a model call that fails or times out  -> retried (llm_client.max_retries)
- a run that costs too much              -> hard stop at llm_client.budget_usd
- a model that returns broken JSON       -> one retry with a correction note
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from northstar.config import ROOT, path, settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """The model could not give a usable answer (after retries)."""


class BudgetExceeded(LLMError):
    """The run hit the spending limit. Stops the run on purpose."""


class CacheMiss(LLMError):
    """Replay mode, and this exact call was never recorded."""


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    from_cache: bool = False


@dataclass
class Usage:
    """Running totals for one run, read by evaluation and economics."""
    calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0               # what the run costs (replayed answers count at their recorded price)
    spent_usd: float = 0.0              # new money actually spent in this run (used for the limit)
    by_model: dict[str, float] = field(default_factory=dict)


# A transport sends one request and returns the raw answer. The real one calls
# OpenRouter; tests pass a fake one, so the test suite never needs the network.
Transport = Callable[[dict[str, Any]], dict[str, Any]]


def _openrouter_transport(timeout_s: float) -> Transport:
    from openai import OpenAI

    client = OpenAI(base_url=settings()["llm_client"]["base_url"],
                    api_key=os.environ["OPENROUTER_API_KEY"], timeout=timeout_s, max_retries=0)

    def send(req: dict[str, Any]) -> dict[str, Any]:
        extra = {"usage": {"include": True}}            # OpenRouter returns the real cost
        if req.get("reasoning_effort"):
            extra["reasoning"] = {"effort": req["reasoning_effort"]}
        kw = dict(model=req["model"], messages=req["messages"], temperature=req["temperature"],
                  max_tokens=req["max_tokens"], extra_body=extra)
        if req.get("json"):
            kw["response_format"] = {"type": "json_object"}
        r = client.chat.completions.create(**kw)
        u = r.usage
        return {"text": r.choices[0].message.content or "",
                "input_tokens": getattr(u, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(u, "completion_tokens", 0) or 0,
                "cost_usd": float(getattr(u, "cost", 0.0) or 0.0)}

    return send


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


class LLMClient:
    def __init__(self, mode: Optional[str] = None, transport: Optional[Transport] = None,
                 cache_dir=None, budget_usd: Optional[float] = None, sleep: Callable[[float], None] = time.sleep):
        cfg = settings()["llm_client"]
        _load_dotenv()
        mode = mode or cfg.get("mode", "auto")
        if mode == "auto":
            mode = "live" if (transport or os.environ.get("OPENROUTER_API_KEY")) else "replay"
        if mode not in ("live", "replay"):
            raise ValueError(f"Unknown llm_client mode '{mode}' (use auto, live or replay)")
        self.mode = mode
        self.cache_dir = cache_dir or path("llm_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.budget = cfg["budget_usd"] if budget_usd is None else budget_usd
        self.max_retries = cfg["max_retries"]
        self._timeout = cfg["timeout_s"]
        self._transport = transport
        self._sleep = sleep
        self.usage = Usage()

    # -- public ------------------------------------------------------------
    def chat(self, model: str, messages: list[dict[str, str]], *, temperature: float = 0.0,
             max_tokens: int = 800, reasoning_effort: Optional[str] = None, json_mode: bool = False) -> LLMResponse:
        req = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens,
                   reasoning_effort=reasoning_effort, json=json_mode)
        key = self._key(req)
        cached = self._read_cache(key)
        if cached is not None:
            self.usage.cache_hits += 1
            return self._record(LLMResponse(**cached, from_cache=True))
        if self.mode == "replay":
            raise CacheMiss(f"Replay mode: no recorded answer for this call to {model}. "
                            "Run once in live mode (with OPENROUTER_API_KEY) to record it.")
        if self.usage.spent_usd >= self.budget:
            raise BudgetExceeded(f"Spending limit reached: ${self.usage.spent_usd:.2f} of ${self.budget:.2f}.")

        transport = self._transport or _openrouter_transport(self._timeout)
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                raw = transport(req)
            except Exception as e:  # timeout, rate limit, network: retry with a short wait
                last_err = e
                if attempt < self.max_retries:
                    self._sleep(2 ** attempt)
                continue
            resp = LLMResponse(text=raw["text"], model=model, input_tokens=raw.get("input_tokens", 0),
                               output_tokens=raw.get("output_tokens", 0), cost_usd=raw.get("cost_usd", 0.0),
                               latency_ms=round((time.perf_counter() - t0) * 1000, 1))
            self._write_cache(key, resp)
            self.usage.spent_usd += resp.cost_usd
            return self._record(resp)
        raise LLMError(f"Model call to {model} failed after {self.max_retries + 1} attempts: {last_err}")

    def chat_json(self, model: str, messages: list[dict[str, str]], schema: Type[T], **kw) -> tuple[T, LLMResponse]:
        """Ask for JSON and check it against a contract. One retry with a correction note."""
        resp = self.chat(model, messages, json_mode=True, **kw)
        try:
            return schema.model_validate_json(_strip_fences(resp.text)), resp
        except (ValidationError, ValueError) as e:
            fix = messages + [{"role": "assistant", "content": resp.text},
                              {"role": "user", "content": "Your answer did not match the required JSON format: "
                               f"{str(e)[:400]}. Reply again with valid JSON only, no other text."}]
            resp2 = self.chat(model, fix, json_mode=True, **kw)
            try:
                return schema.model_validate_json(_strip_fences(resp2.text)), resp2
            except (ValidationError, ValueError) as e2:
                raise LLMError(f"Invalid JSON from {model} after one correction: {str(e2)[:300]}") from e2

    # -- internals -----------------------------------------------------------
    def _record(self, r: LLMResponse) -> LLMResponse:
        u = self.usage
        u.calls += 1
        u.input_tokens += r.input_tokens
        u.output_tokens += r.output_tokens
        u.cost_usd += r.cost_usd
        u.by_model[r.model] = u.by_model.get(r.model, 0.0) + r.cost_usd
        return r

    @staticmethod
    def _key(req: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(req, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]

    def _read_cache(self, key: str) -> Optional[dict[str, Any]]:
        f = self.cache_dir / f"{key}.json"
        if not f.exists():
            return None
        d = json.loads(f.read_text(encoding="utf-8"))
        return {k: d[k] for k in ("text", "model", "input_tokens", "output_tokens", "cost_usd", "latency_ms")}

    def _write_cache(self, key: str, r: LLMResponse) -> None:
        d = {k: getattr(r, k) for k in ("text", "model", "input_tokens", "output_tokens", "cost_usd", "latency_ms")}
        (self.cache_dir / f"{key}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _strip_fences(text: str) -> str:
    """Some models wrap JSON in ```json fences even in JSON mode."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    return t.strip()


if __name__ == "__main__":
    # Quick check that your key works:  python -m northstar.llm --model <openrouter-model-id>
    import argparse
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Send one tiny test message through OpenRouter.")
    ap.add_argument("--model", required=True, help="OpenRouter model id, e.g. from openrouter.ai/models")
    ap.add_argument("--text", default="Reply with the single word: ready")
    a = ap.parse_args()
    c = LLMClient(mode="live")
    r = c.chat(a.model, [{"role": "user", "content": a.text}], max_tokens=20)
    print(f"answer: {r.text!r}\nlatency: {r.latency_ms} ms   tokens in/out: {r.input_tokens}/{r.output_tokens}   cost: ${r.cost_usd:.6f}")
