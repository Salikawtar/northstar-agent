"""Router: the receptionist of the agent.

Reads the conversation and decides, in one model call:
- which of the 10 request types it is (plus any extra requests),
- whether a person must take over now, and why,
- the customer's language, and how sure it is.

It never answers the customer. The prompt lives in prompts/router/ (versioned),
the model and effort in config/settings.yaml, so neither is hard-coded here.

If the model fails or returns something unusable after one correction, the
router does not crash: it sends the chat to a person (fail safe).

Quick check on the validation chats (needs OPENROUTER_API_KEY the first time,
then replays for free):
    python -m northstar.agent.router --split validation
    python -m northstar.agent.router --split validation --model compare_small
    python -m northstar.agent.router --split validation --prompt router/v2.md --effort none
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from northstar.config import path, settings
from northstar.contracts import EscalationReason, Language, RequestType, RouterOutput
from northstar.data import load_conversations
from northstar.llm import LLMClient, LLMError


def load_prompt(rel: str) -> str:
    text = (path("prompts_dir") / rel).read_text(encoding="utf-8")
    if text.startswith("<!--"):                       # drop the version comment on line 1
        text = text.split("-->", 1)[1]
    return text.strip()


def resolve_model(name: str) -> str:
    """Accepts a tier name from settings (small, large, compare_small) or a full OpenRouter id."""
    return settings()["models"].get(name, name)


def format_conversation(turns: list[tuple[str, str]]) -> str:
    return "\n".join(f"{'Customer' if who == 'customer' else 'Agent'}: {text}" for who, text in turns)


def turns_from_row(row: pd.Series) -> list[tuple[str, str]]:
    return [("customer", row["turn_1_customer"]), ("agent", row["turn_2_agent"]), ("customer", row["turn_3_customer"])]


@dataclass
class RouteResult:
    output: RouterOutput
    latency_ms: float
    cost_usd: float
    input_tokens: int
    output_tokens: int
    fallback: bool = False        # True = model failed, chat sent to a person by default
    error: str = ""


class Router:
    def __init__(self, client: Optional[LLMClient] = None, model: Optional[str] = None,
                 reasoning_effort: Optional[str] = None, prompt: Optional[str] = None):
        cfg = settings()["components"]["router"]
        self.client = client or LLMClient()
        self.model = resolve_model(model or cfg["tier"])
        self.effort = reasoning_effort or cfg.get("reasoning_effort")
        self.max_tokens = cfg.get("max_tokens", 1500)
        self.prompt_name = prompt or cfg["prompt"]
        self.system = load_prompt(self.prompt_name)

    def route(self, turns: list[tuple[str, str]], language_hint: Optional[str] = None) -> RouteResult:
        messages = [{"role": "system", "content": self.system},
                    {"role": "user", "content": "Conversation:\n" + format_conversation(turns)}]
        t0 = time.perf_counter()
        try:
            out, resp = self.client.chat_json(self.model, messages, RouterOutput,
                                              reasoning_effort=self.effort, max_tokens=self.max_tokens)
            return RouteResult(out, resp.latency_ms, resp.cost_usd, resp.input_tokens, resp.output_tokens)
        except LLMError as e:
            # Fail safe: never guess. A person picks it up with whatever we know.
            lang = Language(language_hint) if language_hint in ("en", "fr") else Language.EN
            safe = RouterOutput(request_type=RequestType.NEEDS_HUMAN, needs_escalation=True,
                                escalation_reason=EscalationReason.TOOL_FAILURE, confidence=0.0, language=lang)
            return RouteResult(safe, round((time.perf_counter() - t0) * 1000, 1), 0.0, 0, 0, fallback=True, error=str(e)[:300])


# ---------------------------------------------------------------------------
# Development check: how well does the router do on a split of the dataset?
# (Libo's evaluation module does the full, graded evaluation in Phase 4.)
# ---------------------------------------------------------------------------
def evaluate(split: str = "validation", model: Optional[str] = None, router: Optional[Router] = None,
             prompt: Optional[str] = None, effort: Optional[str] = None) -> tuple[pd.DataFrame, dict]:
    router = router or Router(model=model, prompt=prompt, reasoning_effort=effort)
    df = load_conversations(split)
    rows = []
    for _, r in df.iterrows():
        res = router.route(turns_from_row(r), language_hint=r["language"])
        o = res.output
        rows.append(dict(id=r["id"], gold_type=r["request_type"], pred_type=o.request_type.value,
                         gold_escalation=bool(r["needs_escalation"]), pred_escalation=o.needs_escalation,
                         pred_reason=o.escalation_reason.value, gold_language=r["language"], pred_language=o.language.value,
                         secondary=",".join(t.value for t in o.secondary_types), confidence=o.confidence,
                         difficulty=r["difficulty"], adversarial_type=r["adversarial_type"] if isinstance(r["adversarial_type"], str) else "",
                         latency_ms=res.latency_ms, cost_usd=res.cost_usd, input_tokens=res.input_tokens,
                         output_tokens=res.output_tokens, fallback=res.fallback, error=res.error))
    out = pd.DataFrame(rows)
    out["type_correct"] = out.gold_type == out.pred_type
    esc = out[out.gold_escalation]
    pred_esc = out[out.pred_escalation]
    summary = dict(
        model=router.model, prompt=router.prompt_name, reasoning_effort=router.effort, split=split, n=len(out),
        type_accuracy=round(out.type_correct.mean(), 3),
        escalation_recall=round(esc.pred_escalation.mean(), 3) if len(esc) else None,      # of chats that needed a person, how many got one
        escalation_precision=round(pred_esc.gold_escalation.mean(), 3) if len(pred_esc) else None,  # of chats sent to a person, how many needed it
        language_accuracy=round((out.gold_language == out.pred_language).mean(), 3),
        accuracy_by_difficulty={k: round(v, 3) for k, v in out.groupby("difficulty").type_correct.mean().items()},
        fallbacks=int(out.fallback.sum()),
        latency_ms_median=round(out.latency_ms.median(), 1), latency_ms_p90=round(out.latency_ms.quantile(0.9), 1),
        cost_usd_total=round(out.cost_usd.sum(), 5), cost_usd_per_chat=round(out.cost_usd.mean(), 6),
        replayed_from_cache=router.client.usage.cache_hits,
    )
    return out, summary


def _main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Run the router on a dataset split and report accuracy, latency and cost.")
    ap.add_argument("--split", default="validation", choices=["train", "validation", "test"])
    ap.add_argument("--model", default=None, help="small | large | compare_small | an OpenRouter id (default: settings)")
    ap.add_argument("--prompt", default=None, help="prompt file under prompts/, e.g. router/v2.md (default: settings)")
    ap.add_argument("--effort", default=None, help="reasoning effort: none | low | medium | high (default: settings)")
    a = ap.parse_args()
    if a.split == "test":
        print("Note: the test split is for the final evaluation. Tune prompts on validation only.")
    out, summary = evaluate(a.split, a.model, prompt=a.prompt, effort=a.effort)
    res_dir = path("results_dir"); res_dir.mkdir(parents=True, exist_ok=True)
    prompt_v = summary["prompt"].split("/")[-1].removesuffix(".md")
    tag = f"router_{summary['model'].split('/')[-1]}_{prompt_v}_{summary['reasoning_effort']}_{a.split}"
    out.to_csv(res_dir / f"{tag}.csv", index=False)
    (res_dir / f"{tag}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    wrong = out[~out.type_correct][["id", "gold_type", "pred_type", "difficulty"]]
    if len(wrong):
        print("\nWrong request type:\n" + wrong.to_string(index=False))
    print(f"\nSaved: {res_dir / tag}.csv and .json")


if __name__ == "__main__":
    _main()
