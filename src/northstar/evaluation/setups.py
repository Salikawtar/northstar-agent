"""The setups the final evaluation compares, each one a small change from the main agent.

Why this file exists: the brief asks for controlled comparisons that change one thing at a
time. Each setup below names the ONE thing it changes from `full_agent` (the agent we
recommend), so a difference in the results can only come from that change.

| Setup                       | The one change from full_agent                        |
|-----------------------------|-------------------------------------------------------|
| full_agent                  | (reference: settings.yaml as it is)                   |
| full_agent_router_sonnet    | router model: Claude Sonnet 5.5 instead of Haiku 5.5   |
| full_agent_router_finetuned | router model: Neeraj's fine-tuned XLM-RoBERTa          |
| full_agent_router_v2        | router prompt version: v2 instead of v3                |
| full_agent_warranty_high    | reasoning effort of the warranty desk: high, not medium|
| full_agent_no_guardrails    | input and output checks switched off                  |
| single_agent                | architecture: one Sonnet agent with every tool        |

Adding a setup is one entry in SETUPS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from northstar.agent.router import Router, RouteResult, resolve_model
from northstar.config import ROOT, settings
from northstar.contracts import EscalationReason, Language, RequestType, RouterOutput, SetupId


@dataclass(frozen=True)
class Setup:
    """How to build one setup. Only the fields that differ from the main agent are set."""
    name: str
    changes: str                                 # the one change, in plain words (goes in the tables)
    architecture: str = "multi_agent"            # multi_agent | single_agent
    router_model: Optional[str] = None           # tier name or "finetuned"; None = settings
    router_prompt: Optional[str] = None
    desk_effort: dict = field(default_factory=dict)   # e.g. {"warranty_recall": "high"}
    guardrails: bool = True

    def setup_id(self) -> SetupId:
        cfg = settings()["components"]
        if self.architecture == "single_agent":
            sa = cfg["single_agent"]
            return SetupId(name=self.name, router="none", agent_model=resolve_model(sa["tier"]),
                           reasoning_effort=sa["reasoning_effort"],
                           prompt_version=sa["prompt"].split("/")[-1].removesuffix(".md"), architecture="single_agent")
        r = cfg["router"]
        router = ("finetuned" if self.router_model == "finetuned"
                  else f"prompted_{self.router_model or r['tier']}")
        desks = {d: self.desk_effort.get(d, cfg[d]["reasoning_effort"])
                 for d in ("booking_status", "warranty_recall", "billing_lease")}
        return SetupId(name=self.name, router=router,
                       agent_model="; ".join(f"{d}={resolve_model(cfg[d]['tier']).split('/')[-1]}" for d in desks),
                       reasoning_effort="; ".join(f"{d}={e}" for d, e in desks.items()),
                       prompt_version=(self.router_prompt or r["prompt"]).split("/")[-1].removesuffix(".md"),
                       architecture="multi_agent" if self.guardrails else "multi_agent_no_guardrails")


SETUPS: dict[str, Setup] = {s.name: s for s in [
    Setup("full_agent", "reference: the recommended agent (settings.yaml)"),
    Setup("full_agent_router_sonnet", "router model: Sonnet 5.5 instead of Haiku 5.5", router_model="large"),
    Setup("full_agent_router_finetuned", "router model: fine-tuned XLM-RoBERTa instead of Haiku 5.5",
          router_model="finetuned"),
    Setup("full_agent_router_v2", "router prompt: v2 instead of v3", router_prompt="router/v2.md"),
    Setup("full_agent_warranty_high", "warranty desk effort: high instead of medium",
          desk_effort={"warranty_recall": "high"}),
    Setup("full_agent_no_guardrails", "input and output checks off", guardrails=False),
    Setup("single_agent", "architecture: one Sonnet 5.5 agent with every tool, no router", architecture="single_agent"),
]}
MAIN = "full_agent"


# ---------------------------------------------------------------------------
# The fine-tuned router inside the full agent.
# Its checkpoint is 1.1 GB and not in git, so the agent replays the router decisions the
# fine-tuned model made on the 40 test chats (committed by Neeraj in finetune/results/router_test/).
# Same idea as the replay cache for the model calls: the decision is recorded, the rest of the
# agent runs for real. With the checkpoint on disk, the live model is used instead.
# ---------------------------------------------------------------------------
FINETUNED_RECORDING = ROOT / "src" / "northstar" / "finetune" / "results" / "router_test" / \
    "router_finetuned-xlm-roberta-base_none_none_test.csv"


class RecordedRouter:
    """Returns the router decision recorded for a chat id. The harness sets `current_id` first."""

    def __init__(self, recording: Path = FINETUNED_RECORDING, name: str = "finetuned-xlm-roberta-base"):
        self.rows = pd.read_csv(recording).set_index("id")
        self.model, self.prompt_name, self.effort = name, "none", "none"
        self.current_id: Optional[str] = None

    def route(self, turns, language_hint: Optional[str] = None) -> RouteResult:
        r = self.rows.loc[self.current_id]
        reason = EscalationReason(r["pred_reason"]) if bool(r["pred_escalation"]) else EscalationReason.NONE
        out = RouterOutput(request_type=RequestType(r["pred_type"]), needs_escalation=bool(r["pred_escalation"]),
                           escalation_reason=reason, confidence=float(r["confidence"]),
                           language=Language(r["pred_language"]))
        return RouteResult(out, float(r["latency_ms"]), 0.0, int(r["input_tokens"]), 0)


def build_router(setup: Setup, client):
    if setup.router_model == "finetuned":
        ckpt = ROOT / settings()["models"].get("finetuned_router", "models/finetuned_router")
        if (ckpt / "weights.pt").exists():
            from northstar.finetune.predict import FinetunedRouter   # needs torch
            return FinetunedRouter(ckpt)
        return RecordedRouter()
    return Router(client=client, model=setup.router_model, prompt=setup.router_prompt)
