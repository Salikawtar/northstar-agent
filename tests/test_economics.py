"""Cost model tests (Phase 6). Offline, no key: the model only reads committed results."""
import json
import math

import pytest

from northstar.config import ROOT, settings
from northstar.economics import model as em


@pytest.fixture(scope="module")
def summary():
    return em.build()


@pytest.fixture(scope="module")
def ctx():
    return em.assumptions(), settings()["finetuned_router_hosting"], em.measured()


def test_measured_numbers_are_read_not_typed(ctx):
    # The model must use the evaluation's numbers exactly, so the memo and page 5 agree.
    _, _, mes = ctx
    inputs = json.loads((ROOT / "src/northstar/evaluation/results/economics_inputs.json").read_text())
    full = inputs["full_agent"]
    m = mes["small_prompted"]
    assert m["cost_per_reply"] == full["cost_usd_per_chat"]
    assert m["handled_alone_correct"] == full["handled_without_person_and_correct"]
    assert m["wrong_commitment"] == full["wrong_commitment_rate"]
    assert m["wrong_commitment_upper"] == full["wrong_commitment_rate_upper_95"]
    assert mes["finetuned"]["cost_per_reply"] == inputs["full_agent_router_finetuned"]["cost_usd_per_chat"]


def test_status_quo_is_simple_arithmetic(ctx):
    a, _, _ = ctx
    sq = a["status_quo"]
    per_min = sq["advisor_wage_cad_per_hour"] * (1 + sq["payroll_overhead"]) / a["currency"]["cad_per_usd"] / 60
    assert em.status_quo(1000, a)["people"] == pytest.approx(1000 * sq["minutes_per_chat"] * per_min)


def test_breakeven_volume_is_where_the_saving_changes_sign(summary, ctx):
    a, h, mes = ctx
    v = summary["breakeven"]["volume"]["small_prompted"]
    assert em.saving(v, a, mes["small_prompted"], "small_prompted", 0.0, h) > 0
    assert em.saving(v - 300, a, mes["small_prompted"], "small_prompted", 0.0, h) < 0


def test_breakeven_expensive_promise_rate_zeroes_the_saving(summary, ctx):
    a, h, mes = ctx
    r = summary["breakeven"]["expensive_promise_rate"]["100000"]
    s = em.saving(100_000, a, mes["small_prompted"], "small_prompted", r, h)
    assert abs(s) < 0.01 * em.status_quo(100_000, a)["total"]


def test_pilot_cannot_pay_for_expensive_promises(ctx):
    # A person approves every money reply in the pilot, so the expensive-promise rate has no effect.
    a, h, mes = ctx
    m = mes["small_prompted_pilot"]
    assert em.agent_month(20_000, a, m, "small_prompted_pilot", 0.5, h)["mistakes_expensive_promise"] == 0


def test_more_volume_never_raises_cost_per_chat_much(ctx):
    a, h, mes = ctx
    per_chat = [em.agent_month(v, a, mes["small_prompted"], "small_prompted", 0.0, h)["total"] / v
                for v in (1_000, 100_000, 1_000_000)]
    assert per_chat[0] > per_chat[1] >= per_chat[2] * 0.99


def test_evidence_counts_match_the_result_files(summary):
    ev, ho = summary["expensive_promise_evidence"], summary["handoff_evidence"]
    assert ev["n"] == 40 + 30 + 75 + 40 and ev["k"] == 0
    assert ho["k"] == 0 and ho["n"] >= 18 + 75


def test_warranty_breakeven_is_saving_over_cost(summary, ctx):
    a, _, _ = ctx
    w = summary["breakeven"]["warranty_automation"]["base"]
    assert w["breakeven_wrong_approval_rate"] == pytest.approx(
        w["saving_per_claim_usd"] / summary["mistake_costs"]["high_severity"], abs=1e-3)


def _fmt(x):
    return f"{x:,.0f}"


def test_memo_and_page7_quote_the_model(summary):
    # Report numbers are typed in prose, so check the key ones against the model output.
    memo = (ROOT / "docs/decision_memo.md").read_text(encoding="utf-8")
    page = (ROOT / "docs/economics.md").read_text(encoding="utf-8")
    be = summary["breakeven"]
    sav = summary["saving_at"]
    unit = {r["option"]: r for r in __import__("csv").DictReader(open(em.OUT / "unit_economics.csv", encoding="utf-8"))}
    for text in (memo, page):
        assert f"{_fmt(be['volume']['small_prompted'])} chats a month" in text
        assert f"${float(unit['small_prompted']['all_in_usd_per_chat_at_100000']):.2f}" in text
        assert f"${summary['status_quo_usd_per_chat']:.2f}" in text
    assert f"${_fmt(sav['20000']['small_prompted'])}" in page
    assert f"${_fmt(sav['100000']['small_prompted'])}" in page
    assert f"{100 * be['expensive_promise_rate']['100000']:.3f}%" in page
    assert f"1 in {be['warranty_automation']['base']['claims_per_wrong_approval_to_break_even']}" in memo
    mc = summary["monte_carlo"]
    clean = next(k for k in mc if k.startswith("as_built_after_clean_pilot"))
    assert f"{round(100 * mc[clean]['20000']['probability_saving_positive'])}% chance" in memo
    assert f"{round(100 * mc['as_built']['20000']['probability_saving_positive'])}% without a pilot" in memo
    assert math.isclose(round(sav["20000"]["small_prompted"] * 12, -3), 133_000)


def test_fresh_check_reprices_the_same_agent_with_fresh_rates(summary, ctx):
    # The fresh held-out set sits beside the base case: its counts come from the evaluation files,
    # and the only difference between its two savings is the price of the missed handoffs.
    a, _, _ = ctx
    f = summary["fresh_set_check"]
    s = json.loads((ROOT / "src/northstar/evaluation/results/summary_fresh.json").read_text())["setups"][f["setup"]]
    assert f["chats"] == s["n"] and f["task_success_k"] == s["task_success"]["k"]
    assert (f["handoffs_made"], f["handoffs_needed"]) == (s["escalation_recall"]["k"], s["escalation_recall"]["n"])
    assert f["missed_handoffs"] == f["handoffs_needed"] - f["handoffs_made"] == s["missed_handoffs"]
    assert f["finished_alone_correct"] == s["handled_without_person_and_correct"]["k"]
    assert f["handoffs_needed_before_review"] + f["handoffs_added_by_review"] == f["handoffs_needed"]
    miss_per_chat = f["missed_handoffs"] / f["chats"] * f["missed_handoff_usd"]
    for v, sav in f["saving_at"].items():
        assert sav["missed_handoffs_not_priced"] - sav["missed_handoffs_priced"] == pytest.approx(int(v) * miss_per_chat, abs=1)
    p = f["pilot"]["saving_usd_per_month"]
    assert p["missed_handoffs_not_priced"] - p["missed_handoffs_priced"] == pytest.approx(
        a["pilot"]["chats_per_month"] * miss_per_chat, abs=1)
    # The base case is still the 40 test chats: the fresh rates are lower, so its saving must be the larger one.
    assert summary["saving_at"]["20000"]["small_prompted"] > f["saving_at"]["20000"]["missed_handoffs_not_priced"]

