"""Output check: runs on every reply before the customer sees it.

What it does (each rule has an id, listed in docs/guardrails.md):
- G-OUT-01 (P-04) A promise no tool backs (coverage, free work, refund, waiver, discount,
  loaner, a booking no tool made) blocks the reply.
- G-OUT-02 (P-02) Personal data that did not come from the customer or from a tool call
  for the verified customer (phone, email, VIN, plate, repair order) blocks the reply:
  it may belong to someone else.
- G-OUT-03 (P-06) Pieces of the assistant's own instructions in the reply (template
  slots, section titles, output field names) block it.
- G-OUT-04 (P-10) Internal rule ids like "(P-01)" are removed from the reply.

A blocked reply is replaced by a short safe reply in the customer's language, and the
chat goes to a person with the reason in the summary. The customer never sees the
blocked text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from northstar.contracts import (AgentAction, AgentReply, EscalationReason, GuardAction, GuardLayer,
                                 GuardrailVerdict, Language)
from northstar.agent.handoff import build_handoff

SAFE_REPLY = {
    "en": "Thank you for your patience. I'm passing your request to a team member, who will get back to you shortly.",
    "fr": "Merci de votre patience. Je transmets votre demande à une personne de notre équipe, qui vous répondra sous peu.",
}

# G-OUT-02: identifiers that point to a person or a vehicle.
_IDENTIFIERS = {
    "phone": re.compile(r"\(?\b\d{3}\)?[ .-]?\d{3}[ .-]\d{4}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "vin": re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"),
    "plate": re.compile(r"\b[A-Z]{4} ?\d{3}\b"),
    "repair order": re.compile(r"\bRO-\d{6}\b", re.I),
}
# G-OUT-03: fragments of our prompts that should never reach a customer.
_PROMPT_LEAK = re.compile(
    r"\{(policy|context)\}|## (How to work|Your output|Rules you must follow|Context from the system)"
    r"|\"?(policy_rules_cited|escalation_reason)\"?\s*:|You are the [\w ]+ assistant of Northstar", re.I)
_RULE_IDS = re.compile(r"\s*\((?:P-\d{2}(?:\s*,\s*|\s+(?:and|et)\s+)?)+\)|\bP-\d{2}\b")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9@.]", "", s.lower())


def _strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)
    elif obj is not None:
        yield str(obj)


@dataclass
class OutputResult:
    reply: AgentReply
    verdicts: list[GuardrailVerdict] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(v.action == GuardAction.BLOCK for v in self.verdicts)

    @property
    def flags(self) -> list[str]:
        return [v.detail.split(":")[0] for v in self.verdicts]


def check_output(reply: AgentReply, turns: list[tuple[str, str]],
                 tool_data: Optional[list[dict[str, Any]]] = None) -> OutputResult:
    """turns: the conversation as the customer wrote it; tool_data: what the tools returned in this turn."""
    verdicts: list[GuardrailVerdict] = []
    text = reply.text

    # G-OUT-04: rule ids are for our logs.
    if _RULE_IDS.search(text):
        text = re.sub(r"\s+([.,!?])", r"\1", _RULE_IDS.sub("", text)).strip()
        verdicts.append(GuardrailVerdict(layer=GuardLayer.OUTPUT, rule_id="P-10", action=GuardAction.REDACT,
                                         detail="G-OUT-04: rule ids removed"))

    # G-OUT-01: declared or detected promises without a backing tool.
    for c in reply.commitments:
        if c.backed_by_tool is None:
            verdicts.append(GuardrailVerdict(layer=GuardLayer.OUTPUT, rule_id="P-04", action=GuardAction.BLOCK,
                                             detail=f"G-OUT-01: promise without a tool behind it: {c.kind.value} ({c.detail})"))

    # G-OUT-02: identifiers the customer did not give and no tool returned.
    known = _norm(" ".join(t for _, t in turns) + " " + " ".join(_strings(tool_data or [])))
    for kind, pat in _IDENTIFIERS.items():
        for m in pat.finditer(text):
            if _norm(m.group(0)) not in known:
                verdicts.append(GuardrailVerdict(layer=GuardLayer.OUTPUT, rule_id="P-02", action=GuardAction.BLOCK,
                                                 detail=f"G-OUT-02: {kind} not given by the customer or a tool: {m.group(0)}"))

    # G-OUT-03: pieces of the prompt.
    m = _PROMPT_LEAK.search(text)
    if m:
        verdicts.append(GuardrailVerdict(layer=GuardLayer.OUTPUT, rule_id="P-06", action=GuardAction.BLOCK,
                                         detail=f"G-OUT-03: part of the instructions in the reply: {m.group(0)[:60]}"))

    if not any(v.action == GuardAction.BLOCK for v in verdicts):
        return OutputResult(reply.model_copy(update={"text": text}), verdicts)

    # Blocked: safe reply and a handoff. A data or prompt leak is treated as a possible attack.
    leak = any(v.rule_id in ("P-02", "P-06") and v.action == GuardAction.BLOCK for v in verdicts)
    reason = EscalationReason.ADVERSARIAL if leak else EscalationReason.POLICY_LIMIT
    why = "; ".join(v.detail for v in verdicts if v.action == GuardAction.BLOCK)
    if reply.handoff:
        reason = reply.handoff.reason if reply.handoff.reason != EscalationReason.NONE else reason
    summary = f"Reply blocked by the output check ({why[:300]}). " + (reply.handoff.summary if reply.handoff else "")
    lang = "fr" if reply.language == Language.FR else "en"
    safe = reply.model_copy(update={
        "text": SAFE_REPLY[lang], "action": AgentAction.ESCALATED, "commitments": [],
        "handoff": build_handoff(reason, reply.request_type, summary,
                                 facts=(reply.handoff.collected_facts if reply.handoff else None))})
    return OutputResult(safe, verdicts)
