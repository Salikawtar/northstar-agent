"""Shared data contracts for the Northstar Motors project.

Every module (router, agents, guardrails, evaluation, fine-tune, economics)
reads and writes these shapes. Why: if a teammate's fine-tuned router returns
the same RouterOutput as the prompted router, we can swap one for the other in
config and compare them on the exact same test cases. Change a contract only
after the team agrees, and bump CONTRACT_VERSION when you do.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

CONTRACT_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Labels. These match the label values in Weidi's dataset exactly, so the
# dataset can be used for routing and grading without any remapping.
# ---------------------------------------------------------------------------
class RequestType(str, Enum):
    BOOK_SERVICE = "book_service"
    REPAIR_STATUS = "repair_status"
    WARRANTY_CLAIM = "warranty_claim"
    RECALL_INQUIRY = "recall_inquiry"
    ROADSIDE_ASSISTANCE = "roadside_assistance"
    PARTS_ORDER = "parts_order"
    BILLING_DISPUTE = "billing_dispute"
    LEASE_END_RETURN = "lease_end_return"
    OUT_OF_SCOPE = "out_of_scope"
    NEEDS_HUMAN = "needs_human"


class EscalationReason(str, Enum):
    NONE = "none"
    SAFETY = "safety"                    # brakes failed, accident, smoke
    BEREAVEMENT = "bereavement"
    LEGAL_THREAT = "legal_threat"
    ADVERSARIAL = "adversarial"          # injection, impersonation, fraud attempt
    CUSTOMER_REQUEST = "customer_request"  # "let me talk to a person"
    POLICY_LIMIT = "policy_limit"        # needs a decision the bot may not make
    VERIFICATION_FAILED = "verification_failed"
    TOOL_FAILURE = "tool_failure"
    LOW_CONFIDENCE = "low_confidence"


class Language(str, Enum):
    EN = "en"
    FR = "fr"


# ---------------------------------------------------------------------------
# Conversation input
# ---------------------------------------------------------------------------
class Message(BaseModel):
    role: str = Field(pattern="^(customer|agent)$")
    text: str


class Conversation(BaseModel):
    conversation_id: str
    messages: list[Message]
    language: Optional[Language] = None  # None = let the router detect it


# ---------------------------------------------------------------------------
# Router (prompted router and Neeraj's fine-tuned router both return this)
# ---------------------------------------------------------------------------
class RouterOutput(BaseModel):
    request_type: RequestType
    secondary_types: list[RequestType] = Field(default_factory=list)  # multi-ask chats
    needs_escalation: bool
    escalation_reason: EscalationReason = EscalationReason.NONE
    confidence: float = Field(ge=0.0, le=1.0)
    language: Language

    @model_validator(mode="after")
    def _reason_matches_flag(self):
        # Catches a common model mistake: needs_escalation=True with no reason.
        # (model_validator, not field_validator: it must run even when the
        # reason is left at its default.)
        if self.needs_escalation and self.escalation_reason == EscalationReason.NONE:
            raise ValueError("needs_escalation is true but escalation_reason is 'none'")
        return self


# ---------------------------------------------------------------------------
# Tools (dealer system). Every tool returns a ToolResult, never raises, so the
# agent always gets something it can reason about, including failures.
# ---------------------------------------------------------------------------
class ToolError(str, Enum):
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"        # caller has not verified the customer
    INVALID_INPUT = "invalid_input"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"                # e.g. slot already taken


class ToolResult(BaseModel):
    tool: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[ToolError] = None
    message: str = ""
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Agent output. The agent must DECLARE any commitment it makes in structured
# form, so the output guardrail can check it against policy instead of trying
# to read intent out of free text.
# ---------------------------------------------------------------------------
class AgentAction(str, Enum):
    ANSWERED = "answered"
    ASKED_CLARIFICATION = "asked_clarification"
    BOOKED = "booked"
    DRAFTED_CLAIM = "drafted_claim"
    ESCALATED = "escalated"
    REFUSED = "refused"


class CommitmentKind(str, Enum):
    APPOINTMENT = "appointment"
    WARRANTY_COVERAGE = "warranty_coverage"
    FEE_WAIVER = "fee_waiver"
    LOANER = "loaner"
    PRICE = "price"
    REFUND = "refund"


class Commitment(BaseModel):
    kind: CommitmentKind
    detail: str
    backed_by_tool: Optional[str] = None  # which tool result supports it, if any


class Urgency(str, Enum):
    EMERGENCY = "emergency"
    HIGH = "high"
    NORMAL = "normal"


class HandoffPayload(BaseModel):
    """What a human advisor receives, so the customer never repeats themselves."""
    reason: EscalationReason
    urgency: Urgency
    queue: str                           # e.g. "service_advisors", "warranty_desk", "roadside"
    summary: str                         # 2 to 4 plain sentences
    request_type: RequestType
    customer_verified: bool
    customer_ref: Optional[str] = None   # masked, e.g. "C-****1275"
    collected_facts: dict[str, str] = Field(default_factory=dict)
    suggested_next_step: str = ""


class AgentReply(BaseModel):
    conversation_id: str
    text: str
    language: Language
    request_type: RequestType
    action: AgentAction
    commitments: list[Commitment] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    policy_rules_cited: list[str] = Field(default_factory=list)  # e.g. ["P-04"]
    handoff: Optional[HandoffPayload] = None

    @model_validator(mode="after")
    def _handoff_when_escalated(self):
        if self.action == AgentAction.ESCALATED and self.handoff is None:
            raise ValueError("action is 'escalated' but no handoff payload was given")
        return self


# ---------------------------------------------------------------------------
# Guardrails (Jessica). Each check returns one verdict; the pipeline logs all.
# ---------------------------------------------------------------------------
class GuardLayer(str, Enum):
    INPUT = "input"
    TOOL = "tool"
    OUTPUT = "output"


class GuardAction(str, Enum):
    PASS = "pass"
    REDACT = "redact"
    BLOCK = "block"
    ESCALATE = "escalate"


class GuardrailVerdict(BaseModel):
    layer: GuardLayer
    rule_id: str                         # matches the numbered operating policy
    action: GuardAction
    detail: str = ""


# ---------------------------------------------------------------------------
# Evaluation (Libo) and economics (Abhi) read these records.
# ---------------------------------------------------------------------------
class SetupId(BaseModel):
    """One experimental setup. Comparisons change one field at a time."""
    name: str                            # e.g. "multi_agent_v3_small"
    router: str                          # "prompted_small" | "prompted_large" | "finetuned"
    agent_model: str
    reasoning_effort: str = "low"        # "low" | "medium" | "high"
    prompt_version: str = "v1"
    architecture: str = "multi_agent"    # "multi_agent" | "single_agent"


class RunRecord(BaseModel):
    conversation_id: str
    setup: SetupId
    reply: Optional[AgentReply] = None   # None if the run crashed
    router_output: Optional[RouterOutput] = None
    guardrail_verdicts: list[GuardrailVerdict] = Field(default_factory=list)
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GradeRecord(BaseModel):
    conversation_id: str
    setup_name: str
    grader: str = Field(pattern="^(llm|human|rule)$")
    resolved_correctly: bool
    policy_followed: bool
    escalation_correct: bool
    invented_facts: bool
    wrong_commitment: bool
    notes: str = ""


# ---------------------------------------------------------------------------
# Dealer system records (mock DMS)
# ---------------------------------------------------------------------------
class Customer(BaseModel):
    customer_id: str
    first_name: str
    last_name: str
    email: str
    phone: str
    language: Language
    city: str
    is_fleet: bool = False
    in_conversations: bool = True        # False = decoy record for PII tests


class Vehicle(BaseModel):
    vin: str
    customer_id: str
    plate: str
    model: str
    year: int
    in_service_date: date
    odometer_km: int
    ownership: str = Field(pattern="^(owned|leased|fleet)$")
    lease_end_date: Optional[date] = None


class RepairOrder(BaseModel):
    ro_number: str
    vin: str
    customer_id: str
    status: str                          # see data_dictionary.md
    opened: date
    promised: Optional[date] = None
    complaint: str
    lines: list[dict[str, Any]] = Field(default_factory=list)
    estimate_cad: float = 0.0
    approved_by_customer: bool = False


class Recall(BaseModel):
    campaign_id: str
    model: str
    year_from: int
    year_to: int
    title: str
    remedy: str
    safety_risk: bool
    parts_available: bool


class WarrantyTerm(BaseModel):
    coverage: str                        # "basic" | "powertrain" | "corrosion"
    years: int
    km: Optional[int]
    excludes: list[str] = Field(default_factory=list)


class Invoice(BaseModel):
    invoice_id: str
    customer_id: str
    ro_number: str
    issued: date
    lines: list[dict[str, Any]]
    total_cad: float
    status: str = Field(pattern="^(paid|unpaid|disputed)$")


class ServiceSlot(BaseModel):
    slot_id: str
    location: str
    start: datetime
    service_type: str                    # "maintenance" | "diagnosis" | "tires"
    available: bool = True
