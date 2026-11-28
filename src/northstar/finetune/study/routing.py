"""From a router's answer to a handoff: which team gets the chat, and does the team's grader accept it.

When a chat needs a person, the router's *reason* picks the team ("queue"): safety -> roadside team, an attack
-> service manager, and so on. The team's grader checks the team against two dataset columns (request type,
and whether the chat is an attack). In the team's end-to-end test the fine-tuned router lost mainly here:
it gave no reason, so attacks reached the wrong team.

These rules are copied from the team repo `Salikawtar/northstar-agent`, commit 0cc6208 (2026-11-26), so every
router option here is scored exactly as the team scores it:
  * REASON_TO_QUEUE and the two overrides ........ agent/handoff.py (ROUTING, build_handoff)
  * the confidence floor (0.55) and needs_human .. agent/pipeline.py, config/settings.yaml
  * TYPE_TO_REASON (the fixed rule of her fine-tuned router) ... finetune/predict.py (REASON_FOR)
  * expected_queues (what the grader accepts) .... evaluation/rules.py
  * DESK_FOR (which desk answers each type) ...... agent/specialist.py
Not copied: the input check (regex) that marks some attacks as adversarial for every router alike, and a
specialist desk changing the reason after it has run. Both are in the team's end-to-end test.
"""
from __future__ import annotations

import re
from typing import Optional

import numpy as np
import pandas as pd

FLOOR = 0.55                       # agent.router_confidence_floor: an unsure router hands the chat to a person

REASON_TO_QUEUE = {
    "safety": "roadside",
    "legal_threat": "service_manager",
    "bereavement": "service_advisors",
    "adversarial": "service_manager",          # a person reviews every attempt
    "customer_request": "service_advisors",
    "policy_limit": "service_advisors",        # overridden below for disputes and warranty
    "low_confidence": "service_advisors",
    "tool_failure": "service_advisors",
    "verification_failed": "service_advisors",
}

TYPE_TO_REASON = {                             # her fine-tuned router's rule; any other type -> customer_request
    "needs_human": "customer_request",
    "roadside_assistance": "safety",
    "billing_dispute": "policy_limit",
    "warranty_claim": "policy_limit",
    "recall_inquiry": "policy_limit",
    "lease_end_return": "policy_limit",
}


DESK_FOR = {                                   # the specialist desk that answers each request type
    "book_service": "booking_status", "repair_status": "booking_status", "parts_order": "booking_status",
    "roadside_assistance": "booking_status", "warranty_claim": "warranty_recall", "recall_inquiry": "warranty_recall",
    "billing_dispute": "billing_lease", "lease_end_return": "billing_lease",
}


def desk_of(request_type: str) -> str:
    """Where a chat the AI keeps ends up: a specialist desk, the fixed out-of-scope reply, or a person."""
    return DESK_FOR.get(request_type, "fixed_reply" if request_type == "out_of_scope" else "person")


def reason_from_type(request_type: str, attack: bool = False) -> str:
    """The reason a model without a reason output gets. With an attack signal, an attack is 'adversarial'."""
    if attack:
        return "adversarial"
    return TYPE_TO_REASON.get(request_type, "customer_request")


def handoff(request_type: str, escalate: bool, reason: str, confidence: float, floor: float = FLOOR) -> tuple:
    """What the team's pipeline does with one router answer: (escalated, reason, queue or None)."""
    if not escalate and confidence < floor:                  # unsure: a person picks it up
        escalate, reason = True, "low_confidence"
    if not escalate and request_type == "needs_human":       # needs_human always goes to a person
        escalate, reason = True, "customer_request"
    if not escalate:
        return False, "none", None
    if reason in (None, "", "none"):
        reason = "customer_request"
    queue = REASON_TO_QUEUE.get(reason, "service_advisors")
    if reason == "policy_limit" and request_type == "billing_dispute":
        queue = "service_manager"                            # contested charges
    elif reason == "policy_limit" and request_type in ("warranty_claim", "recall_inquiry"):
        queue = "warranty_desk"
    return True, reason, queue


def expected_queues(row: pd.Series) -> Optional[set]:
    """The grader's rule: which teams are acceptable for a chat that needs a person (None = any team)."""
    if not bool(row["needs_escalation"]):
        return None
    attack = isinstance(row["adversarial_type"], str) and bool(row["adversarial_type"])
    rtype = row["request_type"]
    if attack and rtype == "roadside_assistance":
        return {"service_manager", "roadside"}
    if attack:
        return {"service_manager"}
    if rtype == "roadside_assistance":
        return {"roadside"}
    if rtype == "billing_dispute":
        return {"service_manager"}
    if rtype == "needs_human":
        return {"service_advisors", "service_manager", "roadside"}
    return None


def route_all(pool: pd.DataFrame, types, escalate, reasons, confidence, floor: float = FLOOR) -> pd.DataFrame:
    """Run handoff() for every chat; also say whether the outcome is right for each chat."""
    rows = []
    for (_, r), t, e, rs, c in zip(pool.iterrows(), types, escalate, reasons, confidence):
        esc, reason, queue = handoff(t, bool(e), rs, float(c), floor)
        exp = expected_queues(r)
        gold = bool(r["needs_escalation"])
        right_team = gold and esc and (exp is None or queue in exp)
        right_desk = desk_of(t) == desk_of(r["request_type"])
        rows.append(dict(id=r["id"], type=t, escalated=esc, reason=reason, queue=queue, gold_escalation=gold,
                         attack=isinstance(r["adversarial_type"], str) and bool(r["adversarial_type"]),
                         right_team=right_team, right_desk=right_desk,
                         # strict: a person and the right team when needed; when not, the AI keeps it AND the
                         # right desk answers (a wrong desk usually fails the team's AI judge)
                         handled_right=right_team if gold else (not esc and right_desk),
                         handled_right_rules=right_team if gold else not esc))   # the rule checks only (no desk)
    return pd.DataFrame(rows)


def handoff_scores(routed: pd.DataFrame) -> dict:
    """Scores of one router option on the handoffs (all counts are chats)."""
    gold, esc = routed["gold_escalation"].values, routed["escalated"].values
    made = int((gold & esc).sum())
    right = int(routed["right_team"].sum())
    attacks = routed["attack"].values
    return dict(handoffs_needed=int(gold.sum()), handoffs_made=made, missed=int(gold.sum()) - made,
                right_team=right, right_team_rate=right / max(1, int(gold.sum())), wrong_team=made - right,
                extra_handoffs=int((esc & ~gold).sum()), handoffs_sent=int(esc.sum()),
                attacks_right_team=int(routed.loc[attacks, "right_team"].sum()), attacks=int(attacks.sum()),
                kept_wrong_desk=int((~gold & ~esc & ~routed["right_desk"].values).sum()),
                handled_right=float(routed["handled_right"].mean()),
                handled_right_rules=float(routed["handled_right_rules"].mean()))


# ---------------------------------------------------------------------------------------------------------
# Language by a word rule (no model): count common French and English words, the larger count wins.
# Words that exist in both languages ("a", "on", "me", "plus"...) are left out on purpose.
# ---------------------------------------------------------------------------------------------------------
FRENCH_WORDS = set("""le la les un une des du de et est je j mon ma mes ton ta votre vos notre nos pour avec sans dans
sur sous pas ne que qui quoi bonjour bonsoir merci voiture véhicule rendez-vous rendez vous nous il elle ils elles c ça
au aux mais ou où si très déjà été suis ai avez avons sont être avoir faire fait peux pouvez puis veux voudrais
aujourd hui demain hier semaine garage pneus facture frais location bien aussi encore comme quand parce cette ce ces
moi lui leur leurs mon s il vous plaît svp oui non""".split())
ENGLISH_WORDS = set("""the an and is are was were i my you your to for with in of it this that these those can could
would should please hi hello thanks thank car vehicle appointment have has had not do does did be been at we our us
get need want from what when where which who how there their they them here just about will just still yes no""".split())
_TOKEN = re.compile(r"[a-zàâäçéèêëîïôöûùüÿœ']+")


def language_rule(text: str) -> str:
    tokens = [t.strip("'") for t in _TOKEN.findall(str(text).lower())]
    fr = sum(t in FRENCH_WORDS for t in tokens)
    en = sum(t in ENGLISH_WORDS for t in tokens)
    return "fr" if fr > en else "en"


def softmax_confidence(type_logits) -> np.ndarray:
    """The tuned model's confidence: the probability it gives its chosen request type (as her router does)."""
    z = np.asarray(type_logits, dtype=float)
    z = z - z.max(axis=-1, keepdims=True)
    p = np.exp(z) / np.exp(z).sum(axis=-1, keepdims=True)
    return p.max(axis=-1)
