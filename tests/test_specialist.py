"""Specialist engine tests with a scripted fake model: offline, free, repeatable.
Each test name says which rule it protects."""
import json

import pytest

from northstar.agent.handoff import mask_customer
from northstar.agent.specialist import Specialist, flag_promises
from northstar.agent.tools import PERMISSIONS, ToolBox
from northstar.contracts import AgentAction, CommitmentKind, EscalationReason, Language, RequestType, RouterOutput
from northstar.data import load_conversations
from northstar.dms.store import DealerSystem
from northstar.llm import LLMClient


@pytest.fixture()
def dms():
    return DealerSystem()


@pytest.fixture()
def customer(dms):
    """A real customer from the mock dealer system: (last name, plate)."""
    c = next(c for c in dms.customers.values() if c["in_conversations"])
    return c["last_name"], dms.vehicle_by_customer[c["customer_id"]]["plate"]


def call(name, **args):
    return {"tool_calls": [{"id": f"c_{name}", "name": name, "arguments": json.dumps(args)}]}


def final(reply="Done.", action="answered", reason="none", summary=""):
    return {"text": json.dumps({"reply": reply, "action": action, "escalation_reason": reason,
                                "summary": summary, "policy_rules_cited": ["P-01"]})}


def scripted(tmp_path, steps, dynamic=None):
    """Plays the model's answers in order. `dynamic(req, i)` can build an answer from the request."""
    seen = []

    def transport(req):
        seen.append(req)
        i = len(seen) - 1
        step = dynamic(req, i) if dynamic else steps[min(i, len(steps) - 1)]
        return {"text": step.get("text", ""), "tool_calls": step.get("tool_calls", []),
                "input_tokens": 1000, "output_tokens": 80, "cost_usd": 0.0002}
    client = LLMClient(mode="live", transport=transport, cache_dir=tmp_path, sleep=lambda s: None)
    return client, seen


def route(rt=RequestType.BOOK_SERVICE, esc=False, reason=EscalationReason.NONE, lang="en"):
    return RouterOutput(request_type=rt, needs_escalation=esc, escalation_reason=reason,
                        confidence=0.9, language=Language(lang))


TURNS = [("customer", "book me in Oakville please")]


def test_verify_then_book_counts_as_backed_appointment(tmp_path, dms, customer):
    last, plate = customer
    slot = dms.list_slots("Oakville", "maintenance").data["slots"][0]["slot_id"]
    client, _ = scripted(tmp_path, [call("verify_customer", last_name=last, plate=plate),
                                    call("book_slot", slot_id=slot), final("You're booked.")])
    res = Specialist("booking_status", client=client).run("c1", TURNS, route(), dms)
    assert res.reply.action == AgentAction.BOOKED and res.verified
    c = res.reply.commitments[0]
    assert c.kind == CommitmentKind.APPOINTMENT and c.backed_by_tool == "book_slot"


def test_booking_fails_without_verification(tmp_path, dms):
    slot = dms.list_slots("Oakville", "maintenance").data["slots"][0]["slot_id"]
    client, _ = scripted(tmp_path, [call("book_slot", slot_id=slot), final("Please give your plate.", "asked_clarification")])
    res = Specialist("booking_status", client=client).run("c2", TURNS, route(), dms)
    assert res.reply.action == AgentAction.ASKED_CLARIFICATION and not res.reply.commitments


def test_model_only_sees_its_own_desks_tools(tmp_path, dms):
    client, seen = scripted(tmp_path, [final()])
    Specialist("booking_status", client=client).run("c3", TURNS, route(), dms)
    names = {t["function"]["name"] for t in seen[0]["tools"]}
    assert names == set(PERMISSIONS["booking_status"]) and "get_invoice" not in names


def test_other_desks_tool_is_refused_in_code(tmp_path, dms):
    client, _ = scripted(tmp_path, [call("get_invoice", ro_number="RO-111111"), final()])
    res = Specialist("booking_status", client=client).run("c4", TURNS, route(), dms)
    assert res.denied_tools == ["get_invoice"]


def test_tool_calls_are_capped_per_turn(tmp_path, dms):
    def loop(req, i):
        return final() if not req.get("tools") else call("list_slots", location="Oakville", service_type="tires")
    client, seen = scripted(tmp_path, [], dynamic=loop)
    res = Specialist("booking_status", client=client).run("c5", TURNS, route(), dms)
    assert res.tool_calls == 6 and res.reply.action == AgentAction.ANSWERED
    assert "tools" not in seen[-1]      # last call offered no tools: answer now


def test_router_escalation_always_wins(tmp_path, dms):
    client, _ = scripted(tmp_path, [final("Help is on the way.", "answered")])
    res = Specialist("booking_status", client=client).run(
        "c6", TURNS, route(RequestType.ROADSIDE_ASSISTANCE, True, EscalationReason.SAFETY), dms)
    h = res.reply.handoff
    assert res.reply.action == AgentAction.ESCALATED and h.urgency.value == "emergency" and h.queue == "roadside"


def test_two_failed_verifications_hand_off(tmp_path, dms):
    client, _ = scripted(tmp_path, [call("verify_customer", last_name="Nobody", plate="ZZZZ 999"),
                                    call("verify_customer", last_name="Nobody", plate="ZZZZ 998"),
                                    final("Those details don't match.", "asked_clarification")])
    res = Specialist("booking_status", client=client).run("c7", TURNS, route(), dms)
    assert res.reply.action == AgentAction.ESCALATED
    assert res.reply.handoff.reason == EscalationReason.VERIFICATION_FAILED and not res.reply.handoff.customer_verified


def test_unusable_final_answer_falls_back_to_a_person(tmp_path, dms):
    client, _ = scripted(tmp_path, [{"text": "sure!"}, {"text": "still not json"}])
    res = Specialist("booking_status", client=client).run("c8", [("customer", "bonjour")], route(lang="fr"), dms)
    assert res.reply.action == AgentAction.ESCALATED and res.reply.handoff.reason == EscalationReason.TOOL_FAILURE
    assert res.reply.text.startswith("Désolé")


def test_promises_are_flagged_but_negations_are_not():
    assert flag_promises("Good news, the repair is covered under warranty and there is no charge.")
    assert not flag_promises("I can't confirm it is covered; the warranty desk decides.")
    assert not flag_promises("Ce n'est pas gratuit, désolé.")
    assert flag_promises("La réparation est couverte? Oui, c'est gratuit.")


def test_unbacked_promise_in_reply_is_recorded(tmp_path, dms):
    client, _ = scripted(tmp_path, [final("No problem, the diagnostic is free of charge.")])
    res = Specialist("booking_status", client=client).run("c9", TURNS, route(), dms)
    assert any(c.backed_by_tool is None and c.kind == CommitmentKind.FEE_WAIVER for c in res.reply.commitments)


def test_customer_reference_is_masked():
    assert mask_customer("cust_en_107474") == "C-****7474"


def test_prompt_is_complete_and_has_no_dataset_chat(tmp_path):
    client, _ = scripted(tmp_path, [final()])
    sp = Specialist("booking_status", client=client)
    system = sp._system(route())
    assert "{policy}" not in system and "{context}" not in system and "P-04" in system
    assert not any(r.turn_1_customer[:60] in system for r in load_conversations().itertuples())


def test_tool_turns_replay_from_recordings(tmp_path, dms, customer):
    last, plate = customer
    client, _ = scripted(tmp_path, [call("verify_customer", last_name=last, plate=plate), final("Verified.")])
    Specialist("booking_status", client=client).run("c10", TURNS, route(), DealerSystem())
    replay = Specialist("booking_status", client=LLMClient(mode="replay", cache_dir=tmp_path))
    res = replay.run("c10", TURNS, route(), DealerSystem())
    assert res.verified and res.reply.text == "Verified."
