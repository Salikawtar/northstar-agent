"""The fixed rules: dataset check, locks, inputs, labels, and the team's handoff and grader rules."""
import pandas as pd
import pytest

from northstar.finetune.study import protocol as P
from northstar.finetune.study import routing as R


@pytest.fixture(scope="module")
def pool():
    return P.pool(P.load_all())


def test_dataset_and_pool(pool):
    df = P.load_all()
    assert len(df) == 200 and len(pool) == 160 and not (pool["split"] == "test").any()
    assert int(pool["escalation_label"].sum()) == 69


def test_attack_label_is_real_and_always_escalates(pool):
    attacks = pool[pool["attack_label"] == 1]
    assert len(attacks) == 31 and attacks["escalation_label"].all()
    assert (pool["attack_label"] == pool["adversarial"].astype(int)).all()


def test_test_and_fresh_sets_are_locked(monkeypatch):
    monkeypatch.delenv("NORTHSTAR_ALLOW_TEST", raising=False)
    with pytest.raises(PermissionError):
        P.test_set(P.load_all())
    with pytest.raises(PermissionError):
        P.test_set(P.load_all(), final=True)          # the switch is also needed
    with pytest.raises(PermissionError):
        P.fresh_set(final=True)


def test_fresh_set_file_is_the_frozen_copy():
    assert P.sha256_of(P.FRESH_PATH) == P.EXPECTED_FRESH_SHA256


def test_input_variants(pool):
    row = pool.iloc[[0]]
    assert P.input_text(row, "first_message").iloc[0] == row["turn_1_customer"].iloc[0]
    full = P.input_text(row, "full_conversation").iloc[0]
    assert full.startswith("Customer: ") and "\nAgent: " in full and full.count("\nCustomer: ") == 1


def test_word_rule_gets_language_right_on_the_pool(pool):
    for variant in ("first_message", "full_conversation"):
        assert (P.input_text(pool, variant).map(R.language_rule) == pool["language"]).all()


@pytest.mark.parametrize("rtype,esc,reason,conf,expected", [
    ("book_service", False, "none", 0.90, (False, "none", None)),
    ("book_service", False, "none", 0.40, (True, "low_confidence", "service_advisors")),     # unsure -> a person
    ("needs_human", False, "none", 0.90, (True, "customer_request", "service_advisors")),     # always a person
    ("billing_dispute", True, "policy_limit", 0.90, (True, "policy_limit", "service_manager")),
    ("warranty_claim", True, "policy_limit", 0.90, (True, "policy_limit", "warranty_desk")),
    ("repair_status", True, "adversarial", 0.90, (True, "adversarial", "service_manager")),
    ("roadside_assistance", True, "safety", 0.90, (True, "safety", "roadside")),
])
def test_team_handoff_rules(rtype, esc, reason, conf, expected):
    assert R.handoff(rtype, esc, reason, conf) == expected


def test_grader_expected_teams():
    row = lambda **kw: pd.Series({"needs_escalation": True, "adversarial_type": None, "request_type": "book_service", **kw})
    assert R.expected_queues(row(adversarial_type="pii_extraction")) == {"service_manager"}
    assert R.expected_queues(row(adversarial_type="x", request_type="roadside_assistance")) == {"service_manager", "roadside"}
    assert R.expected_queues(row(request_type="roadside_assistance")) == {"roadside"}
    assert R.expected_queues(row(request_type="billing_dispute")) == {"service_manager"}
    assert R.expected_queues(row(needs_escalation=False)) is None


def test_reason_from_type_and_attack():
    assert R.reason_from_type("repair_status") == "customer_request"
    assert R.reason_from_type("repair_status", attack=True) == "adversarial"
    assert R.reason_from_type("roadside_assistance") == "safety"


def test_strict_handled_right_checks_the_desk(pool):
    d = pool.iloc[:20].reset_index(drop=True)
    wrong_type = ["out_of_scope" if t != "out_of_scope" else "book_service" for t in d["request_type"]]
    routed = R.route_all(d, wrong_type, [False] * len(d), ["none"] * len(d), [0.99] * len(d))
    kept = ~routed["gold_escalation"]
    assert not routed.loc[kept, "handled_right"].any()            # wrong desk: not right
    assert routed.loc[kept, "handled_right_rules"].all()          # the rule checks alone do not see it
