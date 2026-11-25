"""Evaluation module: graders, metrics, setups and the grader check, offline and free.
Each test name says which part of the rubric (docs/evaluation_rubric.md) it protects."""
import json

import pandas as pd
import pytest

from northstar.contracts import (AgentAction, AgentReply, Commitment, CommitmentKind, EscalationReason, Language,
                                 RequestType, RouterOutput, RunRecord)
from northstar.data import load_conversations
from northstar.dms.store import DealerSystem
from northstar.evaluation import human_check, metrics
from northstar.evaluation.grader import ModelGrader, case_text
from northstar.evaluation.harness import Run
from northstar.evaluation.rules import RuleGrader, expected_queues, reply_language
from northstar.evaluation.setups import MAIN, SETUPS, RecordedRouter
from northstar.agent.handoff import build_handoff
from northstar.llm import LLMClient

TEST = load_conversations("test").set_index("id", drop=False)
RULES = RuleGrader(DealerSystem())


def chat(cid):
    return TEST.loc[cid]


def run_for(cid, text, action=AgentAction.ANSWERED, reason=None, commitments=(), verified=False, tool_data=()):
    row = chat(cid)
    rt = RequestType(row["request_type"])
    handoff = build_handoff(reason, rt, "summary") if action == AgentAction.ESCALATED else None
    rep = AgentReply(conversation_id=cid, text=text, language=Language(row["language"]), request_type=rt,
                     action=action, commitments=list(commitments), handoff=handoff)
    ro = RouterOutput(request_type=rt, needs_escalation=action == AgentAction.ESCALATED,
                      escalation_reason=reason or EscalationReason.NONE, confidence=0.9, language=Language(row["language"]))
    rec = RunRecord(conversation_id=cid, setup=SETUPS[MAIN].setup_id(), reply=rep, router_output=ro, latency_ms=1000.0)
    return Run(rec, dict(path="booking_status", verified=verified, tool_data=list(tool_data)))


def first(pred):
    return TEST[TEST.apply(pred, axis=1)].iloc[0]["id"]


EN_NO_ESC = first(lambda r: r.language == "en" and not r.needs_escalation and r.request_type == "book_service")
EN_ATTACK = first(lambda r: r.language == "en" and isinstance(r.adversarial_type, str) and r.request_type != "roadside_assistance")
EN_SAFETY = first(lambda r: r.request_type == "roadside_assistance" and r.needs_escalation and not isinstance(r.adversarial_type, str))


# --------------------------------------------------------------------------- rules
def test_missed_handoff_fails_the_escalation_check():
    g = RULES.grade(chat(EN_SAFETY), run_for(EN_SAFETY, "Please book a slot with us."))
    assert g["missed_handoff"] and not g["escalation_correct"] and not g["rule_pass"]


def test_extra_handoff_fails_the_escalation_check():
    g = RULES.grade(chat(EN_NO_ESC), run_for(EN_NO_ESC, "A team member will review your request.",
                                             AgentAction.ESCALATED, EscalationReason.CUSTOMER_REQUEST))
    assert g["extra_handoff"] and not g["rule_pass"]


def test_an_attack_must_reach_the_service_manager():
    assert expected_queues(chat(EN_ATTACK)) == {"service_manager"}
    ok = RULES.grade(chat(EN_ATTACK), run_for(EN_ATTACK, "A team member will review this chat.",
                                              AgentAction.ESCALATED, EscalationReason.ADVERSARIAL))
    wrong = RULES.grade(chat(EN_ATTACK), run_for(EN_ATTACK, "A team member will review this chat.",
                                                 AgentAction.ESCALATED, EscalationReason.CUSTOMER_REQUEST))
    assert ok["queue_ok"] and ok["rule_pass"] and wrong["queue_ok"] is False and not wrong["rule_pass"]


def test_a_safety_chat_must_reach_roadside():
    assert expected_queues(chat(EN_SAFETY)) == {"roadside"}


def test_a_promise_no_tool_backs_fails():
    c = Commitment(kind=CommitmentKind.FEE_WAIVER, detail="no charge", backed_by_tool=None)
    g = RULES.grade(chat(EN_NO_ESC), run_for(EN_NO_ESC, "There is no charge for this.", commitments=[c]))
    assert g["unbacked_promises"] and not g["rule_pass"]


def test_another_customers_plate_is_caught():
    row = chat(EN_NO_ESC)
    dms = RULES.dms
    other = next(v for v in dms.vehicles.values() if v["customer_id"] != row["customer_id"])
    g = RULES.grade(row, run_for(EN_NO_ESC, f"The car with plate {other['plate']} is ready."))
    assert g["other_person_data"] and not g["rule_pass"]


def test_wrong_language_and_response_time_are_caught():
    fr = first(lambda r: r.language == "fr" and not r.needs_escalation)
    g = RULES.grade(chat(fr), run_for(fr, "Thank you, we will call you within the hour."))
    assert not g["language_ok"] and g["time_or_person_claims"] and not g["rule_pass"]
    assert reply_language("Merci, je vous réponds avec votre facture.") == "fr"


def test_a_crashed_run_is_a_failed_chat():
    rec = RunRecord(conversation_id=EN_NO_ESC, setup=SETUPS[MAIN].setup_id(), latency_ms=0.0, error="boom")
    g = RULES.grade(chat(EN_NO_ESC), Run(rec, {"path": "crash"}))
    assert g["crashed"] and not metrics.combine(g, None)["success"]


# --------------------------------------------------------------------------- combining grades
GOOD_LLM = dict(resolved_correctly=True, policy_followed=True, escalation_correct=True,
                invented_facts=False, wrong_commitment=False)


def test_success_needs_every_question_to_pass():
    g = RULES.grade(chat(EN_NO_ESC), run_for(EN_NO_ESC, "I can help with that booking. Which day suits you?"))
    assert metrics.combine(g, GOOD_LLM)["success"]
    for bad in ({"resolved_correctly": False}, {"policy_followed": False}, {"invented_facts": True},
                {"wrong_commitment": True}):
        assert not metrics.combine(g, {**GOOD_LLM, **bad})["success"], bad


def test_no_model_grade_counts_against_the_chat():
    g = RULES.grade(chat(EN_NO_ESC), run_for(EN_NO_ESC, "Which day suits you?"))
    c = metrics.combine(g, None)
    assert not c["success"] and not c["graded"]


# --------------------------------------------------------------------------- statistics
def test_wilson_interval_is_honest_at_zero_and_forty():
    lo, hi = metrics.wilson(0, 40)
    assert lo == 0.0 and 0.08 < hi < 0.095          # 0 mistakes in 40 can still mean up to about 9%
    lo, hi = metrics.wilson(40, 40)
    assert hi == 1.0 and 0.9 < lo < 0.92


def test_mcnemar_only_counts_the_chats_where_setups_disagree():
    a = pd.Series([True] * 10 + [False] * 30)
    b = pd.Series([True] * 10 + [False] * 30)
    assert metrics.mcnemar_exact(a, b)["p_value"] == 1.0
    b2 = pd.Series([False] * 10 + [False] * 30)
    t = metrics.mcnemar_exact(a, b2)
    assert t["a_only"] == 10 and t["b_only"] == 0 and t["p_value"] < 0.01


def test_kappa_is_one_for_perfect_agreement_and_none_when_undefined():
    x = pd.Series([True, False, True, False])
    assert human_check.kappa(x, x) == 1.0
    assert human_check.kappa(pd.Series([True] * 4), pd.Series([True] * 4)) is None


# --------------------------------------------------------------------------- setups
def test_every_setup_changes_one_thing_and_has_an_id():
    assert MAIN in SETUPS
    for s in SETUPS.values():
        sid = s.setup_id()
        assert sid.name == s.name and s.changes
    assert SETUPS["full_agent_warranty_high"].setup_id().reasoning_effort.count("high") == 1


def test_recorded_finetuned_router_replays_neerajs_decisions():
    r = RecordedRouter()
    r.current_id = "v3_0001"
    out = r.route([("customer", "anything")]).output
    assert out.request_type == RequestType.WARRANTY_CLAIM and out.confidence == pytest.approx(0.5261)


# --------------------------------------------------------------------------- model grader
def test_grader_sees_tool_results_but_not_the_setup(tmp_path):
    seen = []

    def transport(req):
        seen.append(req)
        return {"text": json.dumps({**GOOD_LLM, "resolved_reason": "ok"}), "input_tokens": 10, "output_tokens": 5,
                "cost_usd": 0.001}
    client = LLMClient(mode="live", transport=transport, cache_dir=tmp_path, sleep=lambda s: None)
    run = run_for(EN_NO_ESC, "Your appointment is free.", tool_data=[{"slot_id": "S-1", "start": "2026-11-18T09:00"}])
    v, cost, err = ModelGrader(client).grade(chat(EN_NO_ESC), run)
    assert v.resolved_correctly and cost == 0.001 and not err
    user = seen[0]["messages"][1]["content"]
    assert "S-1" in user and "full_agent" not in user and "Your appointment is free." in user
    v2, _, _ = ModelGrader(client).grade(chat(EN_NO_ESC), run, repeat=1)     # a separate recording
    assert len(seen) == 2 and "cache_tag" not in json.dumps(seen[1]["messages"])


# --------------------------------------------------------------------------- grader check against people
def test_grader_check_scores_a_filled_sheet(tmp_path, monkeypatch):
    monkeypatch.setattr(human_check, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(human_check, "SHEET", tmp_path / "sheet.xlsx")
    monkeypatch.setattr(human_check, "SECOND", tmp_path / "sheet2.xlsx")
    monkeypatch.setattr(human_check, "KEY", tmp_path / "key.csv")
    ids = list(TEST.id[:12])
    per_chat = pd.DataFrame([dict(setup="full_agent", id=i, case=f"case {i}", success=k % 3 != 0,
                                  **{f"grader_{q}": (k % 3 != 0) if q not in ("invented_facts", "wrong_commitment")
                                     else (k % 3 == 0) for q in human_check.QUESTIONS},
                                  resolved_reason="r", policy_reason="p", invented_reason="i", commitment_reason="c")
                             for k, i in enumerate(ids)])
    human_check.make_sheet(per_chat)
    from openpyxl import load_workbook
    wb = load_workbook(tmp_path / "sheet.xlsx")
    ws = wb["review"]
    assert "full_agent" not in " ".join(str(c.value) for c in ws["B"])       # blind: setup hidden
    key = pd.read_csv(tmp_path / "key.csv").set_index("review_id")
    for row in ws.iter_rows(min_row=2):
        cid = key.loc[row[0].value, "id"]
        good = ids.index(cid) % 3 != 0
        row[2].value = "tester"
        for j, q in enumerate(human_check.QUESTIONS):
            ans = good if q not in ("invented_facts", "wrong_commitment") else not good
            row[3 + j].value = "yes" if ans else "no"
    wb.save(tmp_path / "sheet.xlsx")
    per_chat.drop(columns=["case"]).to_csv(tmp_path / "per_chat.csv", index=False)
    s = human_check.score(tmp_path)
    overall = next(r for r in s["table"] if r["question"] == "overall: all five good"
                   and r["compared"] == "model grader vs person")
    assert s["rows_labelled"] == 12 and overall["agreement"] == 1.0 and overall["kappa"] == 1.0
