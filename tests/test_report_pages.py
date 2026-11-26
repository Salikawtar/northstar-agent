"""Report pages 2 to 7 (docs/report/): one page each, and no number that the files do not hold.

The pages are short prose, so their numbers are typed. These tests read the committed data and results
and check that the pages quote them. The model card of the fine-tuned router is checked the same way
against the final evaluation. Offline, no key."""
import json
import re
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import pytest

from northstar.config import ROOT
from northstar.economics import model as em
from northstar.finetune import compare, report_figure
from northstar.guardrails.evaluate import evaluate as input_check_numbers

PAGES = ROOT / "docs" / "report"
EVAL = ROOT / "src" / "northstar" / "evaluation" / "results"
TUNE = ROOT / "src" / "northstar" / "finetune" / "results"
FT, SMALL, LARGE = "Fine-tuned (XLM-R)", "Small prompted (Haiku)", "Large prompted (Sonnet)"


def page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


def words(text: str) -> list[str]:
    """The words a reader sees: no title line, no table marks, no figure or comment line."""
    lines = [line for line in text.split("\n")[1:]
             if not (line and set(line) <= set("|- ")) and not line.startswith(("![", "<!--"))]
    return [w for w in " ".join(lines).replace("|", " ").split() if w != "·"]


def money(x: float) -> str:
    return f"${x:,.0f}" if x >= 0 else f"-${-x:,.0f}"


def p_text(p: float) -> str:
    """A p-value as the pages print it: two decimals from 0.1 up, three below that, four below 0.001."""
    if p >= 0.995:
        return "1.0"
    places = "0.01" if p >= 0.1 else "0.001" if p >= 0.001 else "0.0001"
    return str(Decimal(str(p)).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def router_test(label: str) -> pd.DataFrame:
    """One router's row-level results on the 40 test chats (the files the model card is built from)."""
    d = pd.read_csv(compare.find(compare.RUNS, compare.ROUTERS[label]), keep_default_na=False)
    for col in ("gold_escalation", "pred_escalation", "type_correct"):
        d[col] = d[col].astype(str).str.lower().eq("true")
    return d


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
                                         ("page4_finetune.md", 455), ("page5_evaluation.md", 615),
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


def test_page4_quotes_the_finetune_results(cost, test_run):
    t = page("page4_finetune.md")
    table = pd.read_csv(TUNE / "comparison_table.csv").set_index("router")
    stats = json.loads((TUNE / "comparison_stats.json").read_text(encoding="utf-8"))
    runs = {k: router_test(k) for k in (FT, SMALL, LARGE)}

    # the head-to-head table
    def accuracy(k):
        low, high = stats["type_accuracy_95ci"][k]
        return f"{100 * table.type_accuracy[k]:.1f}%", f"({100 * low:.0f} to {100 * high:.0f})"

    (a, ra), (b, rb), (c, rc) = accuracy(FT), accuracy(SMALL), accuracy(LARGE)
    assert f"| Request type right (95% range) | {a} {ra} | **{b}** {rb} | {c} {rc} |" in t
    flagged = {k: f"{int((d.gold_escalation & d.pred_escalation).sum())} of {int(d.gold_escalation.sum())}" for k, d in runs.items()}
    assert f"| Needed handoffs flagged | {flagged[FT]} | **{flagged[SMALL]}** | {flagged[LARGE]} |" in t
    ms = {k: f"{table.latency_ms_median[k]:,.0f} ms" for k in runs}
    assert f"| Median time per chat | **{ms[FT]}**, on a CPU | {ms[SMALL]} | {ms[LARGE]} |" in t
    assert table.cost_usd_per_chat[FT] == 0
    assert f"| Cost per 1,000 chats | **$0**, plus a server | ${table.cost_usd_per_1000_chats[SMALL]:.2f} | ${table.cost_usd_per_1000_chats[LARGE]:.2f} |" in t
    whole = [f"{100 * test_run[s]['task_success']['rate']:.1f}%" for s in ("full_agent_router_finetuned", "full_agent", "full_agent_router_sonnet")]
    assert f"| Task success, whole agent | {whole[0]} | **{whole[1]}** | {whole[2]} |" in t
    assert len(runs[FT]) == 40 and "| On the 40 test chats |" in t

    # how it was built
    log = json.loads((TUNE / "training_log.json").read_text(encoding="utf-8"))
    weights = pd.read_csv(TUNE / "datasize_runs.csv").trainable_params.max()
    assert f"{weights / 1e6:.0f} million weights" in t
    assert f"trained on {log['splits']['train']} chats" in t and f"the {log['splits']['validation']} validation chats" in t
    ranking = pd.read_csv(TUNE / "selection_ranking.csv")
    chosen = json.loads((TUNE / "selection_summary.json").read_text(encoding="utf-8"))
    best = ranking[ranking.model == chosen["chosen_model"]]
    assert len(best) == 3 and f"({chosen['chosen_lr']:.0e}, of three)".replace("e-0", "e-") in t
    assert ranking[ranking.model.str.contains("distilbert")].val_macro_f1.max() < best.val_macro_f1.min() and "DistilBERT scored lower" in t
    assert any("mdeberta" in m for m in chosen["excluded"]) and "mDeBERTa crashed" in t
    lora = json.loads((TUNE / "lora_summary.json").read_text(encoding="utf-8"))
    assert f"macro F1 {lora['full_finetuning']['val_macro_f1_mean']:.2f} against {lora['lora']['val_macro_f1_mean']:.2f}" in t
    full_recall = pd.read_csv(TUNE / "final_seed_runs.csv").val_escalation_recall.mean()
    lora_runs = pd.read_csv(TUNE / "lora_runs.csv")
    lora_recall = lora_runs[lora_runs.lr == lora["lora_best_lr"]].val_escalation_recall.mean()
    assert f"handoff recall {100 * full_recall:.0f}% against {100 * lora_recall:.0f}%" in t
    assert f"At most {log['epochs']} epochs" in t and f"batch {log['batch_size']}" in t
    assert f"weight decay {log['weight_decay']}" in t and f"dropout {log['dropout']}" in t
    assert f"{log['total_gpu_minutes_all_runs']:.0f} GPU minutes in all" in t

    # why it lost
    chats = pd.read_csv(ROOT / "data/conversations/conversations.csv")
    train = chats[chats.split == "train"]
    assert len(train) / train.request_type.nunique() == 13 and "About 13 training chats per request type" in t
    seeds = log["test_type_accuracy_over_seeds"]
    assert len(log["seeds"]) == 5 and f"five training runs ranged from {100 * seeds['min']:g}% to {100 * seeds['max']:g}% on test" in t
    size = json.loads((TUNE / "datasize_summary.json").read_text(encoding="utf-8"))
    assert f"about {size['gain_per_doubling_points']:.0f} points each time the data doubles" in t
    assert f"about {size['chats_to_close_test_gap_if_trend_holds']} chats would close the gap" in t
    attacks = {k: d[d.difficulty == "adversarial"] for k, d in runs.items()}
    right = {k: int(d.type_correct.sum()) for k, d in attacks.items()}
    assert f"{right[FT]} of {len(attacks[FT])} attack chats labelled right (Haiku {right[SMALL]}, Sonnet {right[LARGE]})" in t
    missed = runs[FT][runs[FT].gold_escalation & ~runs[FT].pred_escalation]
    assert len(missed) == 2 and (missed.difficulty == "adversarial").all() and "both handoffs it missed were attacks" in t
    inside = pd.read_csv(EVAL / "per_chat.csv")
    inside = inside[inside.setup == "full_agent_router_finetuned"]
    made = inside[inside.gold_escalation & inside.escalated]
    wrong_queue = int((made.queue_ok.astype(str) == "False").sum())
    assert f"{wrong_queue} of its {len(made)} needed handoffs went to the wrong queue" in t
    versus = json.loads((EVAL / "summary.json").read_text(encoding="utf-8"))["comparisons_with_full_agent"]
    v = next(x for x in versus if x["setup"] == "full_agent_router_finetuned")
    assert v["only_setup_right"] == 0 and f"lost {v['only_full_agent_right']} chats and won none (p = {p_text(v['p_value'])})" in t
    paired = stats["paired_tests_type_accuracy"][f"{FT} vs {SMALL}"]
    assert f"the gap to Haiku is not clear (p = {p_text(paired['p_value'])})" in t
    assert round(table.latency_ms_median[SMALL] / table.latency_ms_median[FT]) == 10 and "10 times faster than Haiku" in t

    # when it pays
    be = json.loads((TUNE / "breakeven.json").read_text(encoding="utf-8"))["base_case"]
    assert f"One CPU server is ${be['monthly_fixed_usd']:.0f} a month" in t
    assert f"above {be['vs_haiku_chats_per_month']:,} chats a month and Sonnet above {be['vs_sonnet_chats_per_month']:,}" in t
    home = cost["northstar_volume"]
    assert f"At Northstar's {home:,} the Haiku router costs ${home * table.cost_usd_per_chat[SMALL]:.0f} a month" in t
    agent = cost["breakeven"]["finetuned_router_inside_agent"]
    assert f"saves ${agent['router_saving_usd_per_conversation']:.4f} a chat" in t
    assert f"finishes {agent['containment_loss_points']:.0f} points fewer chats alone and correctly" in t
    assert f"worth ${agent['people_cost_of_that_loss_usd_per_conversation']:.2f} a chat in people's time" in t

    # the figure draws the same files
    n = report_figure.numbers()
    assert n["breakeven"] == {SMALL: be["vs_haiku_chats_per_month"], LARGE: be["vs_sonnet_chats_per_month"]}
    assert n["northstar_volume"] == home and n["test_accuracy"][FT] == table.type_accuracy[FT]
    assert [x for x, _ in n["curve"]][-1] == log["splits"]["train"]
    assert "(../../src/northstar/finetune/results/page4_figure.png)" in t and (TUNE / "page4_figure.png").exists()


def test_page4_figure_is_drawn_from_the_result_files(tmp_path):
    pytest.importorskip("matplotlib")
    out = tmp_path / "page4_figure.png"
    report_figure.draw(report_figure.numbers(), out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    # wide and short, so it fits the page: the same shape as the copy kept in the repository
    def shape(path):
        raw = path.read_bytes()
        return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")

    assert shape(out) == shape(TUNE / "page4_figure.png") and shape(out)[0] > 3 * shape(out)[1]


def test_page5_quotes_the_evaluation(test_run, fresh_run):
    t = page("page5_evaluation.md")
    summary = json.loads((EVAL / "summary.json").read_text(encoding="utf-8"))
    versus = {c["setup"]: c for c in summary["comparisons_with_full_agent"]}
    names = {"full_agent": "**Recommended agent**", "full_agent_before_fixes": "Before the fixes",
             "full_agent_router_sonnet": "Router: Sonnet 5.5", "full_agent_router_finetuned": "Router: fine-tuned",
             "full_agent_router_v2": "Router prompt v2", "full_agent_warranty_high": "Warranty: high effort",
             "full_agent_no_guardrails": "Checks off", "single_agent": "Single Sonnet agent"}
    assert list(test_run) == list(names) and "Eight setups, one change each" in t      # every setup of the evaluation, in its order

    # the table: one row per setup
    for setup, name in names.items():
        s = test_run[setup]
        ok, hand = s["task_success"], s["escalation_recall"]
        success, span = f"{100 * ok['rate']:.1f}%", f"({100 * ok['ci_low']:.0f} to {100 * ok['ci_high']:.0f})"
        handoffs, wait, usd = f"{hand['k']} of {hand['n']}", f"{s['latency_s_median']:.1f} s", f"${s['cost_usd_per_1000_chats']:.2f}"
        if setup == "full_agent":
            row = f"| {name} | **{success}** {span} | **{handoffs}** | {wait} | **{usd}** | |"
        else:
            v = versus[setup]
            row = f"| {name} | {success} {span} | {handoffs} | {wait} | {usd} | {v['only_full_agent_right']}, {v['only_setup_right']} ({p_text(v['p_value'])}) |"
        assert row in t, row

    # the test set
    chats = pd.read_csv(ROOT / "data/conversations/conversations.csv")
    test = chats[chats.split == "test"]
    assert f"{len(test)} held-out chats ({int((test.difficulty == 'adversarial').sum())} attacks, " \
           f"{int((test.language == 'fr').sum())} in French, {int(test.needs_escalation.astype(bool).sum())} needing a person)" in t

    # reading it
    agent, single = test_run["full_agent"], test_run["single_agent"]
    assert all(s["task_success"]["k"] <= agent["task_success"]["k"] for s in test_run.values()) and "No change beats the recommended agent" in t
    assert f"{100 * agent['handled_without_person_and_correct']['rate']:.0f}% of chats alone and correctly" in t
    assert f"90th-percentile wait {agent['latency_s_p90']:.1f} s" in t
    assert agent["wrong_commitments"]["k"] == agent["invented_facts"]["k"] == 1 and agent["wrong_commitments"]["ci_high"] == agent["invented_facts"]["ci_high"]
    assert f"Its 1 wrong promise and 1 invented fact in {agent['n']} could each be as high as {100 * agent['wrong_commitments']['ci_high']:.1f}%" in t
    clear = [setup for setup, v in versus.items() if v["p_value"] < 0.05]
    assert clear == ["full_agent_before_fixes", "full_agent_router_finetuned", "single_agent"]
    assert "Three gaps are clear at 5%: the fixes, the fine-tuned router and the single agent" in t
    assert f"missed {single['escalation_recall']['n'] - single['escalation_recall']['k']} handoffs at three times the cost" in t
    assert round(single["cost_usd_per_1000_chats"] / agent["cost_usd_per_1000_chats"]) == 3
    assert test_run["full_agent_no_guardrails"]["task_success"]["k"] == agent["task_success"]["k"] and "The checks do not change success here" in t

    # the grader against people, and against itself
    check = json.loads((EVAL / "grader_check.json").read_text(encoding="utf-8"))

    def versus_person(question, who):
        return next(r for r in check["table"] if r["question"] == question and r["compared"] == f"model grader vs {who}")

    first, second = (versus_person("overall: all five good", who) for who in ("person", "second person"))
    assert f"kappa {first['kappa']:.2f} and {second['kappa']:.2f} (target 0.6)" in t
    assert f"each labelled {check['rows_labelled']} replies blind" in t
    assert all(versus_person("escalation_correct", who)["agreement"] == 1 for who in ("person", "second person")) and "on handoffs 100%" in t
    promises = versus_person("wrong_commitment", "person")
    assert f"Wrong promises are too rare to check ({promises['human_yes']} in {promises['n']})" in t
    again = pd.read_csv(EVAL / "grader_consistency_summary.csv").set_index("question")
    assert f"over three passes {100 * again.agreement['all five good']:.1f}%" in t
    by = pd.read_csv(EVAL / "grader_check_by_setup.csv").set_index("setup")
    people = sorted({by.person["full_agent"], by.second_person["full_agent"]})
    assert len(people) == 1 and f"People gave the agent {100 * people[0]:g}%, not {100 * by.final_grade['full_agent']:g}%" in t
    low, high = sorted([by.person["single_agent"], by.second_person["single_agent"]])
    assert f"the single agent {100 * low:g}% to {100 * high:g}%, not {100 * by.final_grade['single_agent']:g}%" in t

    # the error analysis: its table of causes is in docs/evaluation_results.md
    results = (ROOT / "docs/evaluation_results.md").read_text(encoding="utf-8")
    causes = [line for line in results.split("\n") if re.match(r"\| [A-I] \|", line)]
    fixed = [line for line in causes if "**Fixed (D-32)" in line]
    before = test_run["full_agent_before_fixes"]["task_success"]
    assert f"The first, blind run scored {100 * before['rate']:.1f}%" in t
    assert f"Its {before['n'] - before['k']} failures fell into {len(causes)} causes, and {len(fixed)} were fixed in code" in t
    assert causes[0].split("|")[3].strip().startswith("5:") and "standing (5 chats)" in t
    assert len(causes) - len(fixed) == 5 and "Five causes are left" in t
    v = versus["full_agent_before_fixes"]
    assert f"{100 * agent['task_success']['rate']:.1f}% on test ({v['only_full_agent_right']} chats fixed, {v['only_setup_right']} broken)" in t
    val = json.loads((EVAL / "summary_validation.json").read_text(encoding="utf-8"))["setups"]
    assert f"{100 * val['full_agent_before_fixes']['task_success']['rate']:.1f}% to {100 * val['full_agent']['task_success']['rate']:.1f}% on validation" in t
    assert "| Hand-written chats | 40 of 40 | 40 of 40 |" in results
    assert "| Red team (75 attacks) | 75 resisted, 75 handed to a person | 75 resisted, 75 handed to a person |" in results
    assert "hand-written chats and red team unchanged" in t

    # the fresh set
    f = fresh_run["full_agent"]
    ok, hand = f["task_success"], f["escalation_recall"]
    assert f"ran {f['n']} fresh chats once" in t
    assert f"{100 * ok['rate']:.1f}% ({100 * ok['ci_low']:.0f} to {100 * ok['ci_high']:.0f}), {hand['k']} of {hand['n']} handoffs" in t
    assert f["wrong_commitments"]["k"] == f["invented_facts"]["k"] == 0 and "no wrong promise or invented fact" in t
    assert f"{len(test)} and {f['n']} chats: one chat moves a rate by {100 / len(test):g} to {100 / f['n']:.0f} points" in t


def test_model_card_gives_the_end_to_end_result(test_run):
    """The model card used to say the fine-tuned router did about as well as Haiku inside the agent. That came
    from the routing step alone. The whole-agent table it now carries is checked here against the final evaluation."""
    card = (ROOT / "src/northstar/finetune/MODEL_CARD.md").read_text(encoding="utf-8")
    chats = pd.read_csv(EVAL / "per_chat.csv")
    order = ["full_agent_router_finetuned", "full_agent", "full_agent_router_sonnet"]     # the card's columns

    def row(label, cell, bold=True):
        a, b, c = (cell(s) for s in order)
        return f"| {label} | {a} | {'**' + b + '**' if bold else b} | {c} |"

    def success(s):
        ok = test_run[s]["task_success"]
        return f"{100 * ok['rate']:.1f}%", f"({ok['k']} of {ok['n']})"

    a, b, c = (success(s) for s in order)
    assert f"| Task success | {a[0]} {a[1]} | **{b[0]}** {b[1]} | {c[0]} {c[1]} |" in card
    assert row("Needed handoffs made", lambda s: f"{test_run[s]['escalation_recall']['k']} of {test_run[s]['escalation_recall']['n']}") in card

    def made(s):
        d = chats[chats.setup == s]
        return d[d.gold_escalation & d.escalated]

    assert row("...of which reached the right queue", lambda s: f"{int((made(s).queue_ok.astype(str) != 'False').sum())} of {len(made(s))}") in card
    assert row("Handoffs that were not needed", lambda s: str(test_run[s]["extra_handoffs"]), bold=False) in card
    assert row("Invented facts", lambda s: str(test_run[s]["invented_facts"]["k"]), bold=False) in card
    assert row("Median wait", lambda s: f"{test_run[s]['latency_s_median']:.1f} s", bold=False) in card
    assert row("Cost per 1,000 chats", lambda s: f"${test_run[s]['cost_usd_per_1000_chats']:.2f}", bold=False) in card

    # the reasons the card gives
    tuned, haiku = (chats[chats.setup == s] for s in order[:2])
    wrong = made(order[0])
    wrong = wrong[wrong.queue_ok.astype(str) == "False"]
    attacks, other = wrong[wrong.adversarial_type.notna()], wrong[wrong.adversarial_type.isna()]
    queues = attacks.queue.value_counts()
    assert f"{len(attacks)} attacks did not reach the service manager ({queues['service_advisors']} went to general advisors, " \
           f"{queues['warranty_desk']} to the warranty desk, {queues['roadside']} to roadside)" in card
    assert len(other) == 1 and other.gold_type.iloc[0] == "roadside_assistance" and other.queue.iloc[0] == "service_advisors"
    assert "1 safety chat went to advisors instead of roadside" in card
    fast = [d[d.path == "fast_path"] for d in (tuned, haiku)]
    assert f"{len(fast[0])} chats got a fixed reply and a handoff with no desk involved ({len(fast[1])} with Haiku)" in card
    assert f"{int((~fast[0].gold_escalation).sum())} of these did not need a person ({int((~fast[1].gold_escalation).sum())} with Haiku)" in card
    fixed = [int(d.path.isin(["fast_path", "out_of_scope"]).sum()) for d in (tuned, haiku)]
    assert f"{fixed[0]} of its {len(tuned)} chats got a fixed reply that no model writes ({fixed[1]} with Haiku)" in card
    usd = [test_run[s]["cost_usd_per_1000_chats"] for s in order[:2]]
    router = pd.read_csv(TUNE / "comparison_table.csv").set_index("router").cost_usd_per_1000_chats[SMALL]
    assert f"falls by {100 * (1 - usd[0] / usd[1]):.0f}%" in card and f"the router is only ${router:.2f} of the ${usd[1]:.2f}" in card
    assert "does about as well as Haiku" not in card

    # the short table in the fine-tune README carries the same line
    readme = (ROOT / "src/northstar/finetune/README.md").read_text(encoding="utf-8")
    assert f"| Whole agent: task success (final evaluation) | {a[0]} | {b[0]} | {c[0]} |" in readme


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
