"""Model grader: judges what rules cannot (was the request resolved, was a fact invented).

Choices (docs/decision_log.md, D-31):
- A model from another vendor (OpenAI GPT-6.2 Sol) grades our Claude agents, so the grader
  does not mark its own family's style as correct (self-preference bias).
- The grader never sees which setup wrote the reply, so it cannot favour one.
- It sees what the tools returned, so "invented" means "not in the tools or the chat",
  not "sounds wrong to the grader".
- Its grades are checked against the team's hand review of the test chats
  (src/northstar/evaluation/human_check.py): percent agreement and Cohen's kappa.

Every call is recorded in the replay cache like the agent's own calls, so grading
replays for free and gives the same grades.
"""
from __future__ import annotations

import json
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field

from northstar.agent.router import format_conversation, load_prompt, resolve_model, turns_from_row
from northstar.config import settings
from northstar.contracts import GradeRecord
from northstar.evaluation.harness import Run
from northstar.llm import CacheMiss, LLMClient, LLMError

MAX_TOOL_CHARS = 6000      # enough for every tool answer we saw in development; longer ones are cut


class GraderVerdict(BaseModel):
    resolved_correctly: bool
    resolved_reason: str = ""
    policy_followed: bool
    rules_broken: list[str] = Field(default_factory=list)
    policy_reason: str = ""
    escalation_correct: bool
    invented_facts: bool
    invented_reason: str = ""
    wrong_commitment: bool
    commitment_reason: str = ""
    tone_ok: bool = True               # reply quality only (P13 tone advice); not part of success
    tone_reason: str = ""


def _labels(row: pd.Series) -> str:
    adv = row["adversarial_type"] if isinstance(row["adversarial_type"], str) else "none"
    return (f"- Request type: {row['request_type']}\n"
            f"- A person should take over: {'yes' if row['needs_escalation'] else 'no'}\n"
            f"- Attack type (if the customer is trying to trick the assistant): {adv}\n"
            f"- Customer language: {row['language']}")


def case_text(row: pd.Series, run: Run) -> str:
    """Everything the grader reads for one chat. Kept in one function so the human review
    sheet shows a person exactly the same facts (human_check.py)."""
    rep = run.record.reply
    cfg = settings()["dms"]
    tools = json.dumps(run.trace.get("tool_data", []), ensure_ascii=False, default=str)
    if len(tools) > MAX_TOOL_CHARS:
        tools = tools[:MAX_TOOL_CHARS] + " ...(cut)"
    handoff = (f"yes, queue {rep.handoff.queue}, reason {rep.handoff.reason.value}" if rep.handoff else "no")
    return (f"Today is {cfg['anchor_date']}. Branches: {', '.join(cfg['locations'])}.\n\n"
            f"## Conversation\n{format_conversation(turns_from_row(row))}\n\n"
            f"## Labels from a person\n{_labels(row)}\n\n"
            f"## What the assistant did\n- Action: {rep.action.value}\n"
            f"- Passed to a person: {handoff}\n"
            f"- Customer verified in this turn: {'yes' if run.trace.get('verified') else 'no'}\n"
            f"- Tools used: {', '.join(rep.tools_used) or 'none'}\n\n"
            f"## What the tools returned\n{tools if run.trace.get('tool_data') else 'nothing'}\n\n"
            f"## The assistant's new reply\n{rep.text}")


class ModelGrader:
    def __init__(self, client: Optional[LLMClient] = None):
        cfg = settings()["components"]["evaluation_grader"]
        self.client = client or LLMClient()
        self.model = resolve_model(cfg["tier"])
        self.effort = cfg.get("reasoning_effort")
        self.max_tokens = cfg.get("max_tokens", 1500)
        self.prompt_name = cfg["prompt"]
        self.system = load_prompt(cfg["prompt"]).replace(
            "{policy}", load_prompt(settings()["agent"]["shared_rules"]))

    def grade(self, row: pd.Series, run: Run, repeat: int = 0) -> tuple[Optional[GraderVerdict], float, str]:
        """Returns (verdict, cost, error). A crashed run has nothing to grade.
        repeat > 0 asks the same question again as a separate recording (grader self-consistency)."""
        if run.record.reply is None:
            return None, 0.0, "no reply to grade (run crashed)"
        try:
            v, resp = self.client.chat_json(self.model, [{"role": "system", "content": self.system},
                                                         {"role": "user", "content": case_text(row, run)}],
                                            GraderVerdict, reasoning_effort=self.effort, max_tokens=self.max_tokens,
                                            cache_tag=f"repeat-{repeat}" if repeat else None)
            return v, resp.cost_usd, ""
        except CacheMiss:
            raise
        except LLMError as e:
            return None, 0.0, str(e)[:200]


def to_grade_record(cid: str, setup: str, v: GraderVerdict) -> GradeRecord:
    """The shared contract other members read (contracts.GradeRecord)."""
    notes = " | ".join(x for x in (v.resolved_reason, v.policy_reason, v.invented_reason, v.commitment_reason) if x)
    return GradeRecord(conversation_id=cid, setup_name=setup, grader="llm", resolved_correctly=v.resolved_correctly,
                       policy_followed=v.policy_followed, escalation_correct=v.escalation_correct,
                       invented_facts=v.invented_facts, wrong_commitment=v.wrong_commitment, notes=notes[:1000])
