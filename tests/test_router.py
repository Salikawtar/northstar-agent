"""Router tests with a fake model, so they run offline and cost nothing."""
import json

import pytest

from northstar.agent.router import Router, evaluate, load_prompt, turns_from_row
from northstar.contracts import EscalationReason, RequestType
from northstar.data import load_conversations
from northstar.llm import LLMClient


def fake_client(tmp_path, answer):
    """answer(request) -> text. Stands in for OpenRouter."""
    def transport(req):
        return {"text": answer(req), "input_tokens": 900, "output_tokens": 60, "cost_usd": 0.0001}
    return LLMClient(mode="live", transport=transport, cache_dir=tmp_path, sleep=lambda s: None)


def ok(**kw):
    d = {"request_type": "book_service", "secondary_types": [], "needs_escalation": False,
         "escalation_reason": "none", "confidence": 0.9, "language": "en"}
    d.update(kw)
    return json.dumps(d)


PROMPTS = ["router/v1.md", "router/v2.md"]


@pytest.mark.parametrize("name", PROMPTS)
def test_prompt_names_all_ten_request_types(name):
    p = load_prompt(name)
    assert all(t.value in p for t in RequestType)


@pytest.mark.parametrize("name", PROMPTS)
def test_prompt_contains_no_dataset_chat(name):
    # Examples in the prompt are invented, so no test (or other) chat can leak into it.
    p = load_prompt(name)
    chats = load_conversations()
    assert not any(row.turn_1_customer[:60] in p for row in chats.itertuples())


def test_route_returns_contract(tmp_path):
    r = Router(client=fake_client(tmp_path, lambda req: ok(request_type="repair_status")), model="small")
    res = r.route([("customer", "is my car ready? RO-123456")])
    assert res.output.request_type == RequestType.REPAIR_STATUS and not res.fallback


def test_no_temperature_is_sent(tmp_path):
    # Claude Haiku 5.5 rejects any temperature, so the router must not send one.
    seen = {}
    def answer(req):
        seen.update(req)
        return ok()
    Router(client=fake_client(tmp_path, answer), model="small").route([("customer", "book me in")])
    assert seen["temperature"] is None and seen["reasoning_effort"] == "low"


def test_unusable_model_answer_sends_chat_to_a_person(tmp_path):
    r = Router(client=fake_client(tmp_path, lambda req: "sorry I cannot"), model="small")
    res = r.route([("customer", "hello")], language_hint="fr")
    assert res.fallback and res.output.needs_escalation
    assert res.output.request_type == RequestType.NEEDS_HUMAN and res.output.language.value == "fr"


def test_escalation_without_reason_is_corrected_or_sent_to_person(tmp_path):
    # needs_escalation true with reason "none" breaks the contract: the client asks once
    # for a fix; if the fix is still wrong, the router fails safe.
    answers = iter([ok(needs_escalation=True), ok(needs_escalation=True, escalation_reason="safety")])
    r = Router(client=fake_client(tmp_path, lambda req: next(answers)), model="small")
    res = r.route([("customer", "brakes failed")])
    assert res.output.escalation_reason == EscalationReason.SAFETY


def test_evaluate_reports_accuracy_and_escalation_recall(tmp_path):
    gold = load_conversations("validation").set_index("turn_1_customer")
    def answer(req):
        first = req["messages"][1]["content"].split("\n")[1][len("Customer: "):]
        g = gold.loc[first]
        reason = "adversarial" if g.needs_escalation else "none"
        return ok(request_type=g.request_type, needs_escalation=bool(g.needs_escalation),
                  escalation_reason=reason, language=g.language)
    r = Router(client=fake_client(tmp_path, answer), model="small")
    out, s = evaluate("validation", router=r)
    assert s["n"] == 30 and s["type_accuracy"] == 1.0 and s["escalation_recall"] == 1.0
    assert s["cost_usd_total"] == pytest.approx(0.003)


def test_replay_with_missing_recording_fails_loudly(tmp_path):
    # A missing recording must not silently become a "send to a person" answer.
    from northstar.llm import CacheMiss
    r = Router(client=LLMClient(mode="replay", cache_dir=tmp_path), model="small")
    with pytest.raises(CacheMiss):
        r.route([("customer", "hello")])
