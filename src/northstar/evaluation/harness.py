"""Evaluation harness: run one setup on every chat of a split and keep a record of each run.

Each chat gives one RunRecord (the shared contract Libo and Abhi read) plus a small
"trace" with what the graders need and the contract does not hold: which path the chat
took, whether the customer was verified, which checks fired, and what the tools returned
(the model grader checks the reply's facts against it).

Model calls go through the replay cache, so a second run of the same setup costs nothing
and gives the same records. Records are written with personal data masked
(guardrails task 8); grading uses the in-memory records, before masking.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional

from northstar.agent.pipeline import Pipeline
from northstar.agent.router import turns_from_row
from northstar.agent.specialist import Specialist
from northstar.config import path
from northstar.contracts import RunRecord
from northstar.data import load_conversations
from northstar.dms.store import DealerSystem
from northstar.evaluation.setups import Setup, build_router
from northstar.guardrails.log_masking import mask_text
from northstar.llm import CacheMiss, LLMClient


@dataclass
class Run:
    record: RunRecord
    trace: dict[str, Any] = field(default_factory=dict)


class Harness:
    def __init__(self, setup: Setup, client: Optional[LLMClient] = None):
        self.setup = setup
        self.client = client or LLMClient()
        self.setup_id = setup.setup_id()
        if setup.architecture == "single_agent":
            self.agent = Specialist("single_agent", client=self.client)
            self.pipeline = None
        else:
            router = build_router(setup, self.client)
            specialists = {d: Specialist(d, client=self.client, reasoning_effort=setup.desk_effort.get(d))
                           for d in ("booking_status", "warranty_recall", "billing_lease")}
            for sp in specialists.values():
                sp.reply_fixes = setup.reply_fixes
            self.pipeline = Pipeline(client=self.client, router=router, specialists=specialists)
            self.pipeline.guarded = setup.guardrails
            self.pipeline.reply_fixes = setup.reply_fixes

    def run_one(self, row) -> Run:
        cid, turns, lang = row["id"], turns_from_row(row), row["language"]
        try:
            if self.pipeline is None:
                res = self.agent.run(cid, turns, None, DealerSystem(), language_hint=lang)
                return Run(RunRecord(conversation_id=cid, setup=self.setup_id, reply=res.reply, router_output=None,
                                     latency_ms=res.latency_ms, input_tokens=res.input_tokens,
                                     output_tokens=res.output_tokens, cost_usd=res.cost_usd, error=res.error or None),
                           dict(path="single_agent", verified=res.verified, guard_flags=[], tool_data=res.tool_data,
                                router_fallback=False, tool_calls=res.tool_calls))
            if hasattr(self.pipeline.router, "current_id"):      # recorded fine-tuned router: look up by chat id
                self.pipeline.router.current_id = cid
            res = self.pipeline.handle(cid, turns, DealerSystem(), language_hint=lang)
            return Run(RunRecord(conversation_id=cid, setup=self.setup_id, reply=res.reply, router_output=res.route,
                                 latency_ms=res.latency_ms, input_tokens=res.input_tokens,
                                 output_tokens=res.output_tokens, cost_usd=res.cost_usd, error=res.error or None),
                       dict(path=res.path, verified=res.verified, guard_flags=res.guard_flags or [],
                            tool_data=res.tool_data or [], router_fallback=res.router_fallback,
                            tool_calls=len(res.reply.tools_used)))
        except CacheMiss:
            raise                     # replay must say a recording is missing, never hide it
        except Exception as e:        # a crash is a result too: it counts as a failed chat
            return Run(RunRecord(conversation_id=cid, setup=self.setup_id, latency_ms=0.0,
                                 error=f"{type(e).__name__}: {str(e)[:300]}"), dict(path="crash", tool_data=[]))

    def run(self, split: str = "test", workers: int = 8) -> list[Run]:
        """Chats are independent (each gets a fresh dealer system), so they run in parallel.
        The order of the records stays the order of the dataset."""
        df = load_conversations(split)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self.run_one, [r for _, r in df.iterrows()]))


def _mask(obj: Any) -> Any:
    """Mask the text values only (masking the JSON line itself would also hit numbers like costs)."""
    if isinstance(obj, str):
        return mask_text(obj)
    if isinstance(obj, dict):
        return {k: _mask(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask(v) for v in obj]
    return obj


def save_runs(runs: list[Run], split: str, name: str) -> None:
    """One JSON line per chat, personal data masked. outputs/ is rebuilt by replay, so not in git."""
    out = path("runs_dir") / split
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"{name}.jsonl", "w", encoding="utf-8") as f:
        for r in runs:
            rec = {"run": r.record.model_dump(mode="json"), "trace": r.trace}
            f.write(json.dumps(_mask(rec), ensure_ascii=False, default=str) + "\n")
