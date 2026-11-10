"""Contracts reject the mistakes models commonly make, before they reach other modules."""
import pandas as pd
import pytest
from pydantic import ValidationError

from northstar.config import path
from northstar.data import load_conversations
from northstar.contracts import (
    AgentAction, AgentReply, EscalationReason, HandoffPayload, RequestType, RouterOutput, Urgency,
)


def test_dataset_labels_match_contract_enum():
    labels = set(load_conversations()["request_type"])
    assert labels == {t.value for t in RequestType}


def test_router_output_valid():
    r = RouterOutput(request_type="warranty_claim", needs_escalation=False, confidence=0.9, language="en")
    assert r.request_type == RequestType.WARRANTY_CLAIM


def test_router_escalation_needs_a_reason():
    with pytest.raises(ValidationError):
        RouterOutput(request_type="roadside_assistance", needs_escalation=True, confidence=0.9, language="en")


def test_router_confidence_bounded():
    with pytest.raises(ValidationError):
        RouterOutput(request_type="parts_order", needs_escalation=False, confidence=1.4, language="fr")


def test_router_rejects_unknown_label():
    with pytest.raises(ValidationError):
        RouterOutput(request_type="insurance", needs_escalation=False, confidence=0.5, language="en")


def test_escalated_reply_requires_handoff():
    with pytest.raises(ValidationError):
        AgentReply(conversation_id="c1", text="Transferring you.", language="en",
                   request_type="roadside_assistance", action="escalated")


def test_escalated_reply_with_handoff_ok():
    h = HandoffPayload(reason=EscalationReason.SAFETY, urgency=Urgency.EMERGENCY, queue="roadside",
                       summary="Brakes failed on highway, customer safe on shoulder.",
                       request_type=RequestType.ROADSIDE_ASSISTANCE, customer_verified=False)
    r = AgentReply(conversation_id="c1", text="Help is on the way.", language="en",
                   request_type="roadside_assistance", action=AgentAction.ESCALATED, handoff=h)
    assert r.handoff.urgency == Urgency.EMERGENCY
