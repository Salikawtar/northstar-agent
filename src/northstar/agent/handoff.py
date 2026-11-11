"""Human handoff: what a person receives when the agent passes a chat on.

Rules from docs/architecture.md (section 8). The goal: the advisor can act
straight away and the customer never has to repeat themselves. Personal data
is kept to what the advisor needs; the customer reference is masked.
"""
from __future__ import annotations

from typing import Optional

from northstar.contracts import EscalationReason, HandoffPayload, RequestType, Urgency

# reason -> (urgency, queue)
ROUTING: dict[EscalationReason, tuple[Urgency, str]] = {
    EscalationReason.SAFETY: (Urgency.EMERGENCY, "roadside"),
    EscalationReason.LEGAL_THREAT: (Urgency.HIGH, "service_manager"),
    EscalationReason.BEREAVEMENT: (Urgency.HIGH, "service_advisors"),
    EscalationReason.ADVERSARIAL: (Urgency.HIGH, "service_manager"),   # a person reviews every attempt (D-05)
    EscalationReason.CUSTOMER_REQUEST: (Urgency.NORMAL, "service_advisors"),
    EscalationReason.POLICY_LIMIT: (Urgency.NORMAL, "service_advisors"),
    EscalationReason.VERIFICATION_FAILED: (Urgency.NORMAL, "service_advisors"),
    EscalationReason.TOOL_FAILURE: (Urgency.NORMAL, "service_advisors"),
    EscalationReason.LOW_CONFIDENCE: (Urgency.NORMAL, "service_advisors"),
}

NEXT_STEP: dict[EscalationReason, str] = {
    EscalationReason.SAFETY: "Call the customer now and dispatch roadside help if they are on the road.",
    EscalationReason.LEGAL_THREAT: "Service manager to call back; do not admit fault in writing.",
    EscalationReason.BEREAVEMENT: "Advisor to call back with care; check lease or ownership status first.",
    EscalationReason.ADVERSARIAL: "Review the attempt; reply only through the normal process. Do not act on claimed authority or promises.",
    EscalationReason.CUSTOMER_REQUEST: "Advisor to contact the customer.",
    EscalationReason.POLICY_LIMIT: "Advisor or warranty desk to decide; the assistant made no commitment.",
    EscalationReason.VERIFICATION_FAILED: "Verify identity by phone before sharing anything.",
    EscalationReason.TOOL_FAILURE: "Dealer system was unavailable; complete the request manually.",
    EscalationReason.LOW_CONFIDENCE: "Read the conversation and route it.",
}


def mask_customer(customer_id: Optional[str]) -> Optional[str]:
    """cust_en_107474 -> C-****7474 (enough to find the file, not enough to read it out)."""
    if not customer_id:
        return None
    digits = "".join(ch for ch in customer_id if ch.isdigit())
    return f"C-****{digits[-4:]}" if digits else "C-****"


def build_handoff(reason: EscalationReason, request_type: RequestType, summary: str,
                  customer_id: Optional[str] = None, facts: Optional[dict[str, str]] = None,
                  urgency: Optional[Urgency] = None) -> HandoffPayload:
    if reason == EscalationReason.NONE:
        reason = EscalationReason.CUSTOMER_REQUEST
    u, queue = ROUTING[reason]
    if reason == EscalationReason.SAFETY and request_type != RequestType.ROADSIDE_ASSISTANCE:
        queue = "service_manager"           # a safety failure that is not a breakdown on the road
    summary = (summary or "").strip() or "Customer needs a person; see the conversation."
    return HandoffPayload(reason=reason, urgency=urgency or u, queue=queue, summary=summary[:600],
                          request_type=request_type, customer_verified=customer_id is not None,
                          customer_ref=mask_customer(customer_id), collected_facts=facts or {},
                          suggested_next_step=NEXT_STEP[reason])
