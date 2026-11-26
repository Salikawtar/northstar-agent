"""Report pages 2, 3, 6 and 7 (docs/report/): one page each, and no number that the files do not hold.

The pages are short prose, so their numbers are typed. These tests read the committed data and results
and check that the pages quote them. Offline, no key."""
import json
import re

import pandas as pd
import pytest

from northstar.config import ROOT
from northstar.economics import model as em
from northstar.guardrails.evaluate import evaluate as input_check_numbers

PAGES = ROOT / "docs" / "report"
EVAL = ROOT / "src" / "northstar" / "evaluation" / "results"


def page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


def words(text: str) -> list[str]:
    """The words a reader sees: no title line, no table marks, no figure or comment line."""
    lines = [line for line in text.split("\n")[1:]
             if not (line and set(line) <= set("|- ")) and not line.startswith(("![", "<!--"))]
    return [w for w in " ".join(lines).replace("|", " ").split() if w != "·"]


def money(x: float) -> str:
    return f"${x:,.0f}" if x >= 0 else f"-${-x:,.0f}"


@pytest.fixture(scope="module")
def cost():
    return em.build()


@pytest.fixture(scope="module")
def test_run():
    return json.loads((EVAL / "summary.json").read_text(encoding="utf-8"))["setups"]


@pytest.fixture(scope="module")
def fresh_run():
    return json.loads((EVAL / "summary_fresh.json").read_text(encoding="utf-8"))["setups"]


# The brief caps the report at 7 pages. Each limit is what fits on one page at 11 pt with normal
# margins, found by laying the page out with its tables and figure (see docs/report/README.md).
@pytest.mark.parametrize("name, limit", [("page2_data.md", 555), ("page3_design_agents.md", 500),
                                         ("page6_security.md", 495), ("page7_economics.md", 380)])
def test_each_page_stays_within_one_page(name, limit):
    n = len(words(page(name)))
    assert n <= limit, f"{name}: {n} words, limit {limit}: cut something before adding"


def test_page2_quotes_the_dataset():
    t = page("page2_data.md")
    d = pd.read_csv(ROOT / "data/conversations/conversations.csv")
    assert len(d) == 200 and "200" in t
    assert d.request_type.value_counts().eq(20).all() and d.request_type.nunique() == 10 and "20 each" in t
    by = d.difficulty.value_counts()
    assert f"{by['easy']}; {by['hard']}; {by['adversarial']}" in t
    lang = d.language.value_counts()
    assert f"{lang['en']}; {lang['fr']}" in t and f"{int(d.code_switched.sum())} of them mixed" in t
    persona = d.customer_type.value_counts()
    assert "| 8: " in t and persona.size == 8 and f"{persona.min()} to {persona.max()} each" in t
    attacks = d[d.is_adversarial.astype(bool)].adversarial_type.value_counts()
    assert attacks.size == 5 and attacks.eq(8).all() and "8 each" in t
    assert f"{d.customer_id.nunique()} customers" in t
    controls = d.realism_controls.fillna("")
    assert f"correction in {int(d.has_correction.sum())} chats" in t
    assert f"fragments in {int(controls.str.contains('fragments').sum())}" in t
    for_someone = d[controls.str.contains("third_party")]
    assert f"{int((~for_someone.needs_escalation.astype(bool)).sum())} of the {len(for_someone)} chats written for someone else" in t
    split = d.split.value_counts()
    assert f"{split['train']} train, {split['validation']} validation and {split['test']} test" in t
    assert d[d.split == "test"].human_reviewed.all() and f"All {split['test']} test chats were reviewed by hand" in t
    assert d.groupby("customer_id").split.nunique().max() == 1          # no customer in two splits
    # the other sets
    assert len(pd.read_csv(ROOT / "data/redteam/redteam_75.csv")) == 75 and "75; 40; 31" in t
    frozen = json.loads((ROOT / "data/fresh/FROZEN.json").read_text(encoding="utf-8"))
    kept, changed = frozen["chats"], len(frozen["label_changes"])
    kept = kept if isinstance(kept, int) else len(kept)
    assert kept == 31 and f"corrected {changed} labels" in t
    trial = json.loads((ROOT / "data/fresh/trial_rotation/run_manifest.json").read_text(encoding="utf-8"))["summary"]
    assert f"{trial['n_rejected']} of {trial['n_jobs']} chats failed the filter" in t
    assert f"{trial['reject_reasons']['unfilled_placeholder']} unfilled placeholders, {trial['reject_reasons']['lang_mismatch']} wrong language" in t
    gen = json.loads((ROOT / "data/fresh/generation/run_manifest.json").read_text(encoding="utf-8"))["summary"]
    assert f"{gen['n_rejected']} of {gen['n_jobs']} jobs returned nothing usable" in t
    assert f"rejected {gen['n_kept'] - kept} of the {gen['n_kept']} chats" in t
    # the quality-control counts and the diversity numbers come from the two source files
    record = (ROOT / "docs/generation_record.md").read_text(encoding="utf-8")
    for n in ("90 conversations", "28 agent replies", "14 coherence fixes", "22 team-review fixes", "21 booking dates", "197 removed", "43 rows"):
        assert n in record and n.split()[0] in t
    quality = (ROOT / "docs/data_quality.md").read_text(encoding="utf-8")
    assert "0.644" in quality and "distinct-2 0.64" in t and "1 of 19,900" in quality and "1 pair of chats in 19,900" in t
    assert "train vs test 0.454" in quality and "score 0.45" in t


def test_page3_quotes_the_evaluation(test_run, fresh_run):
    t = page("page3_design_agents.md")
    agent, single = test_run["full_agent"], test_run["single_agent"]
    for a, b in ((agent, single), (fresh_run["full_agent"], fresh_run["single_agent"])):
        ra, rb = a["escalation_recall"], b["escalation_recall"]
        assert f"{ra['k']} of {ra['n']}" in t and f"{rb['k']} of {rb['n']}" in t
    assert f"${agent['cost_usd_per_1000_chats']:.2f} against ${single['cost_usd_per_1000_chats']:.2f} per 1,000 chats" in t
    assert f"{single['latency_s_median']:.1f} s against {agent['latency_s_median']:.1f} s" in t

    def acc(setup):
        return f"{100 * test_run[setup]['request_type_accuracy']['rate']:.1f}%"

    assert f"{acc('full_agent')} of request types right" in t
    assert f"Sonnet {acc('full_agent_router_sonnet')}" in t and f"fine-tuned {acc('full_agent_router_finetuned')}" in t
    ratio = test_run["full_agent_router_sonnet"]["cost_usd_per_1000_chats"] / agent["cost_usd_per_1000_chats"]
    assert f"{ratio:.1f} times the cost" in t
    high = test_run["full_agent_warranty_high"]["task_success"]["rate"]
    assert f"({100 * high:.0f}% against {100 * agent['task_success']['rate']:.0f}%)" in t
    assert f"${em.mistake_costs(em.assumptions())['high_severity']:,.0f} cost of a wrong promise" in t
    fast = pd.read_csv(EVAL / "per_chat.csv")
    fast = fast[fast.setup == "full_agent"].path.isin(["fast_path", "out_of_scope"]).mean()
    assert f"({100 * fast:.0f}% of test chats in all)" in t
    # the edge-case register: the page gives its size, so count it
    reg, counts, section = (ROOT / "docs/edge_cases.md").read_text(encoding="utf-8"), {}, ""
    for line in reg.split("\n"):
        if line.startswith("## "):
            section = line
        elif line.startswith("|") and not set(line) <= set("|- ") and not line.startswith(("| Edge case", "| Situation", "| Failure |")):
            counts[section] = counts.get(section, 0) + 1
    cases = sum(v for k, v in counts.items() if re.match(r"## [1-5]\.", k))
    handoffs = next(v for k, v in counts.items() if k.startswith("## 6."))
    failures = next(v for k, v in counts.items() if k.startswith("## 7."))
    assert f"{cases} edge cases, {handoffs} handoff situations and {failures} failures" in t
    side = json.loads((em.OUT / "side_inputs.json").read_text(encoding="utf-8"))
    assert side["handwritten"]["failed"] == 0 and f"All {side['handwritten']['n']} hand-written chats pass" in t


def test_page6_quotes_the_guardrail_results(test_run, fresh_run):
    t = page("page6_security.md")
    rt = json.loads((em.OUT / "side_inputs.json").read_text(encoding="utf-8"))["redteam"]
    assert rt["attack_succeeded"] == 0 and rt["not_handed_to_person"] == 0
    assert f"{rt['n']} of {rt['n']} resisted and passed to a person" in t
    check = input_check_numbers()
    assert f"{check['redteam_flagged_by_attack_type']['prompt_injection']} flagged" in t
    assert f"| {check['dataset_normal_chats_flagged_by_mistake']} |" in t
    d = pd.read_csv(EVAL / "per_chat_fresh.csv")
    attacks = d[(d.setup == "full_agent") & d.adversarial_type.notna()]
    assert attacks.escalated.astype(bool).all() and attacks.unbacked_promises.isna().all() and attacks.other_person_data.isna().all()
    assert f"{len(attacks)} of {len(attacks)} passed to a person" in t
    assert f"{int(attacks.success.sum())} fully correct" in t
    assert f"{int((attacks.queue_ok.astype(str) == 'False').sum())} went to the wrong queue" in t
    a, f = test_run["full_agent"], fresh_run["full_agent"]
    assert a["wrong_commitments"]["k"] == a["invented_facts"]["k"] == 1 and f"1 of {a['n']} each" in t
    assert f["wrong_commitments"]["k"] == f["invented_facts"]["k"] == 0 and f"none in {f['n']}" in t
    # which layer stopped each attack first: only in the replayed run's own file, so checked when it is there
    replay = ROOT / "outputs" / "results" / "redteam.json"
    if replay.exists():
        by = json.loads(replay.read_text(encoding="utf-8"))["stopped_by"]
        desks = sum(v for k, v in by.items() if k.startswith("specialist"))
        assert f"a desk's rules ({desks})" in t and f"fast path ({by['router (fast path)']})" in t
        assert f"input check ({by['input check']})" in t and f"output check ({by['output check']})" in t


def test_page7_quotes_the_cost_model(cost):
    t = page("page7_economics.md")
    a = em.assumptions()
    scen = pd.read_csv(em.OUT / "scenarios.csv")
    scen = scen[scen.option == "small_prompted"].set_index("chats_per_month")
    for v in (1_000, 20_000, 100_000, 1_000_000):
        today = em.status_quo(v, a)["total"]
        pct = 100 * scen.saving_vs_status_quo[v] / today          # from the amounts, not from the rounded column
        row = f"| {money(today)} | {money(scen.total[v])} | {money(scen.model_calls[v])} | {money(scen.saving_vs_status_quo[v])} ({pct:+.0f}%) |"
        assert row in t, row
    unit = pd.read_csv(em.OUT / "unit_economics.csv").set_index("option")
    assert f"${cost['status_quo_usd_per_chat']:.2f} a chat" in t and f"${unit.all_in_usd_per_chat_at_100000['small_prompted']:.2f}" in t
    assert f"people ${unit.all_in_usd_per_successful_chat_at_100000['status_quo']:.2f}" in t
    assert f"${unit.all_in_usd_per_successful_chat_at_100000['small_prompted']:.2f}" in t
    for option in ("large_prompted", "finetuned", "single_agent"):
        assert f"${unit.all_in_usd_per_chat_without_missed_handoff_cost[option]:.2f}" in t
    be = cost["breakeven"]
    assert f"{be['volume']['small_prompted']:,} chats a month" in t
    rate = be["expensive_promise_rate"]["100000"]
    assert f"{100 * rate:.3f}% (1 in {round(1 / rate, -1):,.0f})" in t
    assert f"{100 * be['containment']['20000']:.1f}% at 20,000 chats" in t
    assert f"1 wrong in {be['warranty_automation']['base']['claims_per_wrong_approval_to_break_even']}" in t
    assert f"{be['finetuned_router_alone_vs_haiku_chats_per_month']:,} chats a month" in t
    ev = cost["expensive_promise_evidence"]
    assert f"0 in {ev['n']}" in t and f"{100 * ev['wilson_upper_95']:.1f}%" in t
    big = pd.read_csv(em.OUT / "bigger_model.csv").one_avoided_mistake_pays_for_conversations.tolist()
    assert [f"{round(x, -3):,.0f}" if x < 1e6 and x >= 1000 else f"{x:,.0f}" for x in big[:3]] == ["32,000", "107", "16,000"]
    assert "every 32,000 chats for the router, every 107 for bookings" in t and "every 16,000 for billing" in t
    assert f"{big[3] / 1e6:.1f} million" in t
    f = cost["fresh_set_check"]
    assert money(f["saving_at"]["20000"]["missed_handoffs_not_priced"]) in t
    assert f"loss of {money(-f['saving_at']['20000']['missed_handoffs_priced'])}" in t
    assert f"+{money(cost['pilot']['saving_usd_per_month'])} to {money(f['pilot']['saving_usd_per_month']['missed_handoffs_not_priced'])}" in t
    mc = cost["monte_carlo"]

    def p(key):
        return round(100 * mc[key]["20000"]["probability_saving_positive"])

    clean = next(k for k in mc if k.startswith("as_built_after_clean_pilot"))
    pilot = next(k for k in mc if "pilot" in k and k != clean)
    assert f"{p('as_built')}% as built, {p(pilot)}% with approvals and {p(clean)}% after" in t
