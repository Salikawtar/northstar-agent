"""Input check: runs on the customer's messages before any model sees them.

What it does (each rule has an id, listed in docs/guardrails.md):
- G-IN-01 (P-06) Instructions aimed at the assistant ("ignore previous instructions",
  "you are now in admin mode", "show me your prompt"...) are cut out of the message and
  replaced by a marker. The chat is flagged, so a person reviews it (P-08). The rest of
  the message still goes through, because the customer may also have a real request.
- G-IN-02 (privacy) A card number or social insurance number pasted into the chat is
  masked before it reaches the model or the logs. The agent never needs them.
- G-IN-03 Very long messages are cut to a maximum length (cost and injection surface).

It is rules only, no model call: free, instant and predictable. Its weakness is that
reworded attacks get through; the router, the specialist rules and the output check are
the next layers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from northstar.config import settings
from northstar.contracts import GuardAction, GuardLayer, GuardrailVerdict

# G-IN-01: phrases that address the assistant's rules, role or prompt. English and French.
# Each pattern matches the instruction up to the end of its sentence, so only that part is cut.
_TO_END = r"[^.!?\n]*[.!?]?"
INJECTION = [
    rf"\b(ignore|disregard|forget|override)\b[^.!?\n]{{0,30}}\b(previous|prior|above|earlier|all|your|the)\b[^.!?\n]{{0,20}}\b(instructions?|rules?|prompts?|guidelines|policy|policies)\b{_TO_END}",
    rf"\byou are now\b[^.!?\n]{{0,40}}\b(mode|admin|developer|unrestricted|jailbroken|dan|system|assistant without)\b{_TO_END}",
    rf"\b(admin|administrator|developer|debug|god|maintenance|override)\s+mode\b{_TO_END}",
    rf"\bsystem\s*(override|prompt|message|instruction)s?\s*[:\-]{_TO_END}",
    rf"\b(reveal|print|show|repeat|display|output|tell me)\b[^.!?\n]{{0,25}}\b(system prompt|your prompt|your instructions|your rules|hidden instructions|initial instructions)\b{_TO_END}",
    rf"\bnew (instructions|rules|task)\s*:{_TO_END}",
    r"</?\s*(system|assistant|instructions?)\s*>",
    rf"\b(ignore[zr]?|oublie[zr]?)\b[^.!?\n]{{0,30}}\b(instructions?|consignes?|r[eè]gles?)\b{_TO_END}",
    rf"\bmode\s+(admin|administrateur|d[ée]veloppeur|d[ée]bogage)\b{_TO_END}",
    rf"\b(r[ée]v[eè]le[zr]?|affiche[zr]?|montre[zr]?|r[ée]p[eè]te[zr]?)\b[^.!?\n]{{0,25}}\b(tes|vos|les)\s+(instructions|consignes|r[eè]gles)\b{_TO_END}",
    rf"\btu es (maintenant|d[ée]sormais)\b[^.!?\n]{{0,40}}{_TO_END}",
]
_INJECTION = [re.compile(p, re.I) for p in INJECTION]
INJECTION_MARKER = "[removed by the input check: instruction to the assistant]"

# G-IN-02: card numbers (13 to 19 digits, Luhn check) and Canadian SIN (9 digits, Luhn check).
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_SIN = re.compile(r"\b\d{3}[ -]?\d{3}[ -]?\d{3}\b")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


@dataclass
class InputResult:
    turns: list[tuple[str, str]]                       # what the models receive
    verdicts: list[GuardrailVerdict] = field(default_factory=list)

    @property
    def injection(self) -> bool:
        return any(v.detail.startswith("G-IN-01") for v in self.verdicts)

    @property
    def flags(self) -> list[str]:
        return [v.detail.split(":")[0] for v in self.verdicts]


def _mask_numbers(text: str, verdicts: list[GuardrailVerdict]) -> str:
    def card(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            verdicts.append(GuardrailVerdict(layer=GuardLayer.INPUT, rule_id="P-02", action=GuardAction.REDACT,
                                             detail="G-IN-02: card number masked"))
            return "[card number removed]"
        return m.group(0)

    def sin(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) == 9 and _luhn(digits):
            verdicts.append(GuardrailVerdict(layer=GuardLayer.INPUT, rule_id="P-02", action=GuardAction.REDACT,
                                             detail="G-IN-02: social insurance number masked"))
            return "[SIN removed]"
        return m.group(0)

    return _SIN.sub(sin, _CARD.sub(card, text))


def check_input(turns: list[tuple[str, str]]) -> InputResult:
    """Clean the customer's messages. Agent turns are left alone (they are ours)."""
    cfg = settings().get("guardrails", {})
    max_chars = cfg.get("max_message_chars", 2000)
    verdicts: list[GuardrailVerdict] = []
    out = []
    for who, text in turns:
        if not who.lower().startswith("customer"):
            out.append((who, text))
            continue
        if len(text) > max_chars:
            text = text[:max_chars] + " [message cut by the input check]"
            verdicts.append(GuardrailVerdict(layer=GuardLayer.INPUT, rule_id="P-06", action=GuardAction.REDACT,
                                             detail=f"G-IN-03: message longer than {max_chars} characters cut"))
        for pat in _INJECTION:
            for m in list(pat.finditer(text)):
                verdicts.append(GuardrailVerdict(layer=GuardLayer.INPUT, rule_id="P-06", action=GuardAction.ESCALATE,
                                                 detail=f"G-IN-01: instruction to the assistant removed: {m.group(0)[:80]}"))
            text = pat.sub(INJECTION_MARKER, text)
        text = _mask_numbers(text, verdicts)
        out.append((who, text))
    return InputResult(out, verdicts)
