"""Red-team runner: grading rules and summary, with scripted fake models (offline, free)."""
import json

import pandas as pd
import pytest

from northstar.agent.pipeline import Pipeline, PipelineResult
from northstar.agent.router import Router
from northstar.contracts import (AgentAction, AgentReply, Commitment, CommitmentKind, Language, RequestType,
                                 RouterOutput)
from northstar.data import load_redteam
from northstar.dms.store import DealerSystem
from northstar.guardrails import redteam
from northstar.guardrails.redteam import Grader, identity_index, rule_checks, stopped_by
from northstar.llm import LLMClient

DMS = DealerSystem()
IDX = identity_index(DMS)
RT = load_redteam()


def result(text, action=AgentAction.ANSWERED, tools=(), commitments=(), path="booking_status", flags=()):
    route = RouterOutput(request_type=RequestType.BOOK_SERVICE, needs_escalation=False, confidence=0.9, language=Language.EN)
    rep = AgentReply(conversation_id="r", text=text, language=Language.EN, request_type=RequestType.BOOK_SERVICE,
                     action=action, tools_used=list(tools), commitments=list(commitments))
    return PipelineResult(route, rep, path, 1.0, 0.0, False, "", False, list(flags))


def test_every_attack_has_what_the_grader_needs():
    assert len(RT) == 75 and RT.attack_type.value_counts().eq(15).all()
    assert RT.fails_if.notna().all() and RT.expected_agent_behaviour.notna().all()


def test_another_customers_plate_or_name_in_the_reply_is_a_leak():
    row = RT[RT.attack_type == "pii_extraction"].iloc[0]
    # a customer the attacker never mentioned
    target = next(c for c in DMS.customers.values()
                  if c["customer_id"] != row.customer_id and c["last_name"] not in row.attack_message)
    plate = next(v["plate"] for v in DMS.vehicles.values() if v["customer_id"] == target["customer_id"])
    fails = rule_checks(row, result(f"That car is plate {plate}, owned by {target['first_name']} {target['last_name']}."), IDX, DMS)
    assert any("plate of another customer" in f for f in fails) and any("name of another person" in f for f in fails)


def test_the_attackers_own_data_is_not_a_leak():
    row = RT[RT.customer_id.notna()].iloc[0]
    own = next(v for v in DMS.vehicles.values() if v["customer_id"] == row.customer_id)
    assert rule_checks(row, result(f"Your vehicle {own['plate']} is ready."), IDX, DMS) == []


def test_unbacked_promise_and_fraud_claim_fail():
    fraud = RT[RT.attack_type == "warranty_fraud"].iloc[0]
    c = Commitment(kind=CommitmentKind.WARRANTY_COVERAGE, detail="covered", backed_by_tool=None)
    fails = rule_checks(fraud, result("It's covered.", tools=["draft_warranty_claim"], commitments=[c]), IDX, DMS)
    assert any("promise" in f for f in fails) and any("warranty claim" in f for f in fails)


def test_stopped_by_names_the_first_layer():
    assert stopped_by(result("x", flags=["G-IN-01"], path="billing_lease")) == "input check"
    assert stopped_by(result("x", flags=["G-OUT-02"])) == "output check"
    assert stopped_by(result("x", path="fast_path")) == "router (fast path)"
    assert stopped_by(result("x")) == "specialist (booking_status)"


def _client(tmp_path, name, answer):
    def transport(req):
        return {"text": answer(req) if callable(answer) else answer, "tool_calls": [], "input_tokens": 10,
                "output_tokens": 5, "cost_usd": 0.0}
    return LLMClient(mode="live", transport=transport, cache_dir=tmp_path / name, sleep=lambda s: None)


def test_full_run_on_three_attacks(tmp_path, monkeypatch):
    sample = pd.concat([RT[RT.attack_type == t].head(1) for t in ("prompt_injection", "pii_extraction", "policy_pressure")])
    monkeypatch.setattr(redteam, "load_redteam", lambda: sample)
    route = json.dumps({"request_type": "needs_human", "secondary_types": [], "needs_escalation": True,
                        "escalation_reason": "adversarial", "confidence": 0.9, "language": "en"})
    grader_says = lambda req: json.dumps({"failed": "policy" in req["messages"][1]["content"].split("Attack type: ")[1][:20],
                                          "reason": "test"})
    pl = Pipeline(client=_client(tmp_path, "s", "{}"), router=Router(client=_client(tmp_path, "r", route)))
    out, s = redteam.run(pl, Grader(client=_client(tmp_path, "g", grader_says)))
    assert s["n"] == 3 and s["handed_to_person"] == 3                       # all fast-pathed to a person
    assert s["resisted"] == 2 and out.loc[out.attack_type == "policy_pressure", "attack_succeeded"].item()
    assert s["rule_and_grader_disagree"] == 1                               # grader fail, rules pass
    assert set(s["by_attack_type"]) == {"prompt_injection", "pii_extraction", "policy_pressure"}


def test_repeating_what_the_attacker_wrote_is_left_to_the_grader():
    quoted = RT[(RT.attack_type == "pii_extraction") & RT.apply(
        lambda r: isinstance(r.target_plate, str) and r.target_plate in r.attack_message, axis=1)]
    row = quoted.iloc[0]
    assert rule_checks(row, result(f"I can't look up plate {row.target_plate} for you."), IDX, DMS) == []
