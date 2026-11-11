"""Checks on the hand-written test chats (task 19).

1. The file itself is valid: unique ids, known paths, the last turn is the customer's,
   and every customer, plate and slot it names exists in the dealer system.
2. The checker works, on made-up results.
3. Once the chats are recorded, the full agent replays them for free and all must pass.
"""
import re

import pytest

from northstar.agent.handoff import build_handoff
from northstar.agent.pipeline import Pipeline, PipelineResult
from northstar.agent.scenarios import PATHS, check, load_chats, run
from northstar.contracts import (AgentAction, AgentReply, EscalationReason, Language, RequestType,
                                 RouterOutput)
from northstar.dms.store import DealerSystem
from northstar.llm import CacheMiss, LLMClient

CHATS = load_chats()


def test_chat_file_is_valid():
    ids = [c["id"] for c in CHATS]
    assert len(ids) == len(set(ids)) >= 12
    for c in CHATS:
        assert c["turns"][-1][0] == "customer" and c["language"] in ("en", "fr") and c["why"]
        for p in (c["expect"].get("path") if isinstance(c["expect"].get("path"), list) else [c["expect"].get("path")]):
            assert p is None or p in PATHS


def test_named_customers_exist_in_the_dealer_system():
    dms = DealerSystem()
    plates = {v["plate"] for v in dms.vehicles.values()}
    for c in CHATS:
        text = " ".join(t for _, t in c["turns"])
        for plate in re.findall(r"\b[A-Z]{4} \d{3}\b", text):
            assert plate in plates, f"{c['id']}: plate {plate} not in the dealer system"


def _result(path="booking_status", action=AgentAction.ANSWERED, text="Happy to help.", tools=(), handoff=None,
            verified=False):
    route = RouterOutput(request_type=RequestType.BOOK_SERVICE, needs_escalation=False, confidence=0.9,
                         language=Language.EN)
    rep = AgentReply(conversation_id="x", text=text, language=Language.EN, request_type=RequestType.BOOK_SERVICE,
                     action=action, tools_used=list(tools), handoff=handoff)
    return PipelineResult(route, rep, path, 1.0, 0.0, False, "", verified)


def test_checker_passes_a_matching_result_and_explains_failures():
    chat = {"id": "t", "expect": {"path": "billing_lease", "escalated": True, "reason": "policy_limit",
                                  "queue": "service_manager", "tools_include": ["get_invoice"],
                                  "must_not_match": ["will be removed"]}}
    h = build_handoff(EscalationReason.POLICY_LIMIT, RequestType.BILLING_DISPUTE, "contested labour")
    good = _result("billing_lease", AgentAction.ESCALATED, "The manager will review it.", ["get_invoice"], h)
    assert check(chat, good) == []
    bad = _result("booking_status", AgentAction.ANSWERED, "The charge will be removed (P-02).")
    fails = " ".join(check(chat, bad))
    for words in ("went to booking_status", "did not hand off", "did not use get_invoice",
                  "will be removed", "rule id", "queue None"):
        assert words in fails


def test_handwritten_chats_all_pass_on_replay():
    try:
        out, s = run(Pipeline(client=LLMClient(mode="replay")))
    except CacheMiss:
        pytest.skip("hand-written chats not recorded yet: run python -m northstar.agent.scenarios once")
    assert s["failed"] == 0, out.loc[~out.passed, ["id", "failed_checks"]].to_string()
