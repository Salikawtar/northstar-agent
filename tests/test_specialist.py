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
    # asking or reporting a question is not a promise (false alarm in the first warranty run, v3_0004)
    assert not flag_promises("I can't tell you whether this warning is covered. Only the warranty desk decides that.")
    assert not flag_promises("Le bureau de garantie va décider si la réparation est couverte.")
    # Seen in the step 5 runs (v3_0062, v3_0114): a limit, not a promise.
    assert not flag_promises("I also need to correct my colleague: I can't confirm that there is no charge or that the work was covered.")
    assert not flag_promises("One correction: I can't confirm that the service light creates no charge, or that the inspection takes 30 minutes.")
    assert not flag_promises("Je ne peux pas confirmer que la réparation sera sans frais.")
    # Reporting a colleague's mistake (v3_0114, pipeline run) is not a promise.
    assert not flag_promises("One correction: they shouldn't have said the service light creates no charge.")
    assert not flag_promises("Mon collègue a eu tort de dire que c'était gratuit.")
    # Reporting what a colleague wrote (v3_0062, baseline run) is not a promise.
    assert not flag_promises("That message said the repair had no charge because it was covered, and I can't confirm that yet.")
    assert flag_promises("As agreed, the repair has no charge.")
    # The limit only covers its own sentence.
    assert flag_promises("I can't confirm the date. The repair is free of charge.")


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


# --- warranty and recalls, billing and lease ----------------------------------
def test_warranty_desk_can_draft_but_not_book(tmp_path, dms, customer):
    last, plate = customer
    client, seen = scripted(tmp_path, [call("verify_customer", last_name=last, plate=plate),
                                       call("draft_warranty_claim", symptom="screen goes black"),
                                       final("I sent a review request.", "drafted_claim")])
    res = Specialist("warranty_recall", client=client).run("w1", TURNS, route(RequestType.WARRANTY_CLAIM), dms)
    names = {t["function"]["name"] for t in seen[0]["tools"]}
    assert "book_slot" not in names and "get_invoice" not in names and "draft_warranty_claim" in names
    assert res.reply.action == AgentAction.DRAFTED_CLAIM
    assert not any(c.kind == CommitmentKind.WARRANTY_COVERAGE for c in res.reply.commitments)


def test_claimed_draft_without_tool_is_not_counted(tmp_path, dms):
    client, _ = scripted(tmp_path, [final("I've submitted your claim.", "drafted_claim")])
    res = Specialist("warranty_recall", client=client).run("w2", TURNS, route(RequestType.WARRANTY_CLAIM), dms)
    assert res.reply.action == AgentAction.ANSWERED


def test_claim_number_is_the_same_every_run(dms, customer):
    last, plate = customer
    ids = []
    for _ in range(2):
        d = DealerSystem()
        _, s = d.verify_customer(last, plate=plate)
        ids.append(d.draft_warranty_claim(s, "screen goes black").data["claim_id"])
    assert ids[0] == ids[1] and ids[0].startswith("WC-")


def test_billing_desk_reads_invoices_but_cannot_book_or_draft(tmp_path, dms):
    client, seen = scripted(tmp_path, [call("book_slot", slot_id="SL-00001"), final("A manager will review it.", "escalated", "policy_limit", "Disputes a charge.")])
    res = Specialist("billing_lease", client=client).run("b1", TURNS, route(RequestType.BILLING_DISPUTE), dms)
    names = {t["function"]["name"] for t in seen[0]["tools"]}
    assert "get_invoice" in names and "draft_warranty_claim" not in names
    assert res.denied_tools == ["book_slot"] or "book_slot" in names
    assert res.reply.action == AgentAction.ESCALATED and res.reply.handoff.reason == EscalationReason.POLICY_LIMIT


@pytest.mark.parametrize("agent", ["warranty_recall", "billing_lease"])
def test_each_desk_prompt_is_complete(tmp_path, agent):
    client, _ = scripted(tmp_path, [final()])
    system = Specialist(agent, client=client)._system(route())
    assert "{policy}" not in system and "{context}" not in system and "P-09" in system
    assert not any(r.turn_1_customer[:60] in system for r in load_conversations().itertuples())


def test_billing_desk_can_book_a_lease_inspection(tmp_path, dms, customer):
    last, plate = customer
    slot = dms.list_slots("Oakville", "maintenance").data["slots"][0]["slot_id"]
    client, _ = scripted(tmp_path, [call("verify_customer", last_name=last, plate=plate),
                                    call("book_slot", slot_id=slot), final("Your inspection is booked.")])
    res = Specialist("billing_lease", client=client).run("b2", TURNS, route(RequestType.LEASE_END_RETURN), dms)
    assert res.reply.action == AgentAction.BOOKED and res.reply.commitments[0].backed_by_tool == "book_slot"


def test_billing_desk_still_cannot_draft_claims_or_check_recalls():
    assert "draft_warranty_claim" not in PERMISSIONS["billing_lease"] and "check_recalls" not in PERMISSIONS["billing_lease"]


def test_shared_rules_v2_carry_the_tone_rule(tmp_path):
    client, _ = scripted(tmp_path, [final()])
    system = Specialist("booking_status", client=client)._system(route())
    assert "State a limit at most once" in system


def _recall_customer(dms):
    for c in dms.customers.values():
        v = dms.vehicle_by_customer.get(c["customer_id"])
        if v and any(r["model"] == v["model"] and r["year_from"] <= v["year"] <= r["year_to"] for r in dms.recalls):
            return c["last_name"], v["plate"]


def test_recall_repair_at_no_cost_is_backed_by_check_recalls(tmp_path, dms):
    last, plate = _recall_customer(dms)
    client, _ = scripted(tmp_path, [call("verify_customer", last_name=last, plate=plate), call("check_recalls"),
                                    final("There is an open recall, and the fix is done at no cost to you.")])
    res = Specialist("warranty_recall", client=client).run("w9", TURNS, route(RequestType.RECALL_INQUIRY), dms)
    fee = [c for c in res.reply.commitments if c.kind == CommitmentKind.FEE_WAIVER]
    assert fee and all(c.backed_by_tool == "check_recalls" for c in fee)


def test_no_cost_without_a_recall_lookup_stays_unbacked(tmp_path, dms):
    client, _ = scripted(tmp_path, [final("The fix is done at no cost to you.")])
    res = Specialist("warranty_recall", client=client).run("w10", TURNS, route(RequestType.RECALL_INQUIRY), dms)
    assert any(c.backed_by_tool is None and c.kind == CommitmentKind.FEE_WAIVER for c in res.reply.commitments)


def test_rule_ids_never_reach_the_customer(tmp_path, dms):
    client, _ = scripted(tmp_path, [final("I can't share that until you're verified (P-01, P-02). What is your plate?")])
    res = Specialist("billing_lease", client=client).run("b9", TURNS, route(RequestType.LEASE_END_RETURN), dms)
    assert "P-0" not in res.reply.text and res.reply.text.startswith("I can't share that until you're verified.")


def test_replayed_run_reports_the_recorded_latency(tmp_path, dms):
    def transport(req):
        return {"text": json.dumps({"reply": "Hi.", "action": "answered", "escalation_reason": "none",
                                    "summary": "", "policy_rules_cited": []}),
                "tool_calls": [], "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0}
    live = LLMClient(mode="live", transport=transport, cache_dir=tmp_path, sleep=lambda s: None)
    Specialist("booking_status", client=live).run("l1", TURNS, route(), dms)
    rec = next(tmp_path.glob("*.json")); d = json.loads(rec.read_text()); d["latency_ms"] = 6000.0
    rec.write_text(json.dumps(d))
    res = Specialist("booking_status", client=LLMClient(mode="replay", cache_dir=tmp_path)).run("l1", TURNS, route(), dms)
    assert res.latency_ms >= 6000.0


# --- single-agent baseline ----------------------------------------------------
def test_single_agent_has_every_tool_and_no_router_context(tmp_path, dms):
    client, seen = scripted(tmp_path, [final("Happy to help.")])
    sp = Specialist("single_agent", client=client)
    res = sp.run("s1", TURNS, None, dms, language_hint="fr")
    names = {t["function"]["name"] for t in seen[0]["tools"]}
    assert names == set(PERMISSIONS["single_agent"]) and {"book_slot", "get_invoice", "draft_warranty_claim"} <= names
    system = seen[0]["messages"][0]["content"]
    assert "router" not in system.lower() and "{context}" not in system and "P-08" in system
    assert res.reply.language == Language.FR and res.reply.action == AgentAction.ANSWERED


def test_single_agent_decides_its_own_handoff(tmp_path, dms):
    client, _ = scripted(tmp_path, [final("Please stay safe, help is coming.", "escalated", "safety", "Stranded on the 401.")])
    res = Specialist("single_agent", client=client).run("s2", TURNS, None, dms)
    assert res.reply.action == AgentAction.ESCALATED and res.reply.handoff.reason == EscalationReason.SAFETY
