"""Full-agent tests with scripted fake models: offline, free, repeatable.
Each test name says which rule it protects."""
import json

import pytest

from northstar.agent.pipeline import FIXED_REPLY, Pipeline
from northstar.agent.router import Router
from northstar.contracts import AgentAction, EscalationReason, Urgency
from northstar.dms.store import DealerSystem
from northstar.llm import LLMClient

TURNS = [("customer", "hello"), ("agent", "Hi, how can I help?"), ("customer", "please help")]


def route_json(**kw):
    d = {"request_type": "book_service", "secondary_types": [], "needs_escalation": False,
         "escalation_reason": "none", "confidence": 0.9, "language": "en"}
    d.update(kw)
    return json.dumps(d)


def client(tmp_path, name, answer):
    seen = []

    def transport(req):
        seen.append(req)
        return {"text": answer(req), "tool_calls": [], "input_tokens": 900, "output_tokens": 60, "cost_usd": 0.0001}
    return LLMClient(mode="live", transport=transport, cache_dir=tmp_path / name, sleep=lambda s: None), seen


def specialist_final(reply="Happy to help.", action="answered"):
    return json.dumps({"reply": reply, "action": action, "escalation_reason": "none",
                       "summary": "", "policy_rules_cited": ["P-01"]})


def build(tmp_path, router_answer, spec_answer=lambda req: specialist_final()):
    rc, _ = client(tmp_path, "router", lambda req: router_answer)
    sc, seen = client(tmp_path, "spec", spec_answer)
    return Pipeline(client=sc, router=Router(client=rc)), seen


@pytest.mark.parametrize("reason,rtype", [("safety", "roadside_assistance"), ("legal_threat", "billing_dispute"),
                                          ("bereavement", "lease_end_return"), ("customer_request", "repair_status")])
def test_fast_path_skips_the_specialist_and_hands_off(tmp_path, reason, rtype):
    pl, seen = build(tmp_path, route_json(request_type=rtype, needs_escalation=True, escalation_reason=reason))
    res = pl.handle("p1", TURNS, DealerSystem())
    assert res.path == "fast_path" and not seen                  # no specialist model call
    assert res.reply.action == AgentAction.ESCALATED and res.reply.handoff.reason.value == reason
    assert res.reply.text == FIXED_REPLY[reason]["en"]


def test_safety_goes_out_as_an_emergency_in_french(tmp_path):
    pl, _ = build(tmp_path, route_json(request_type="roadside_assistance", needs_escalation=True,
                                       escalation_reason="safety", language="fr"))
    res = pl.handle("p2", TURNS, DealerSystem())
    assert res.reply.handoff.urgency == Urgency.EMERGENCY and "911" in res.reply.text and "sécurité" in res.reply.text


@pytest.mark.parametrize("rtype,desk", [("book_service", "booking_status"), ("parts_order", "booking_status"),
                                        ("recall_inquiry", "warranty_recall"), ("billing_dispute", "billing_lease")])
def test_each_request_type_goes_to_its_desk(tmp_path, rtype, desk):
    pl, seen = build(tmp_path, route_json(request_type=rtype))
    res = pl.handle("p3", TURNS, DealerSystem())
    assert res.path == desk and seen
    assert res.reply.action == AgentAction.ANSWERED and res.reply.handoff is None


def test_contested_charge_gets_a_specialist_reply_then_a_handoff(tmp_path):
    pl, seen = build(tmp_path, route_json(request_type="billing_dispute", needs_escalation=True,
                                          escalation_reason="policy_limit"))
    res = pl.handle("p4", TURNS, DealerSystem())
    assert res.path == "billing_lease" and seen
    assert res.reply.action == AgentAction.ESCALATED and res.reply.handoff.reason == EscalationReason.POLICY_LIMIT


def test_adversarial_without_a_desk_gets_the_fixed_refusal(tmp_path):
    pl, seen = build(tmp_path, route_json(request_type="needs_human", needs_escalation=True,
                                          escalation_reason="adversarial"))
    res = pl.handle("p5", TURNS, DealerSystem())
    assert res.path == "fast_path" and not seen and res.reply.handoff.queue == "service_manager"


def test_out_of_scope_gets_a_polite_redirect_without_handoff(tmp_path):
    pl, seen = build(tmp_path, route_json(request_type="out_of_scope"))
    res = pl.handle("p6", TURNS, DealerSystem())
    assert res.path == "out_of_scope" and not seen and res.reply.handoff is None


def test_unsure_router_sends_the_chat_to_a_person(tmp_path):
    pl, seen = build(tmp_path, route_json(confidence=0.4))
    res = pl.handle("p7", TURNS, DealerSystem())
    assert res.path == "fast_path" and not seen
    assert res.reply.handoff.reason == EscalationReason.LOW_CONFIDENCE


def test_router_failure_falls_back_to_a_person(tmp_path):
    pl, seen = build(tmp_path, "this is not json")
    res = pl.handle("p8", TURNS, DealerSystem())
    assert res.router_fallback and res.path == "fast_path" and not seen
    assert res.reply.handoff.reason == EscalationReason.TOOL_FAILURE


def test_cost_adds_router_and_specialist(tmp_path):
    pl, _ = build(tmp_path, route_json())
    res = pl.handle("p9", TURNS, DealerSystem())
    assert res.cost_usd == pytest.approx(0.0002)


def test_handoff_summary_carries_the_last_customer_message(tmp_path):
    pl, _ = build(tmp_path, route_json(needs_escalation=True, escalation_reason="customer_request"))
    res = pl.handle("p10", TURNS, DealerSystem())
    assert "please help" in res.reply.handoff.summary
