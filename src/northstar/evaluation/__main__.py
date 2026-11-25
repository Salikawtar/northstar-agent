"""Final evaluation in one command (Member 4, experiments and evaluation).

    python -m northstar.evaluation                      # every setup on the 40 test chats: run, grade, tables
    python -m northstar.evaluation --setups full_agent single_agent
    python -m northstar.evaluation --split validation   # same harness on the validation chats (development)
    python -m northstar.evaluation sheet                # rebuild the blind hand-review sheet
    python -m northstar.evaluation check                # model grader vs the team's hand labels (kappa)
    python -m northstar.evaluation consistency          # grade the main agent's test replies 2 more times

What one run does, for each setup (src/northstar/evaluation/setups.py):
1. Runs the 40 test chats through it (harness.py) -> one RunRecord per chat.
2. Grades each reply with rules (rules.py) and with the model grader (grader.py).
3. Combines them into one success grade per chat (metrics.combine) and writes the tables.

Every model call, the grader's included, is recorded in data/llm_cache/, so after the
first run this replays for free with the same numbers (`python run_all.py evaluate`).
The test chats were never used to tune anything (prompt changes are tested on validation).
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from northstar.config import settings
from northstar.data import load_conversations
from northstar.dms.store import DealerSystem
from northstar.evaluation import errors, human_check, metrics
from northstar.evaluation.grader import ModelGrader, case_text, to_grade_record
from northstar.evaluation.harness import Harness, save_runs
from northstar.evaluation.rules import RuleGrader
from northstar.evaluation.setups import MAIN, SETUPS
from northstar.guardrails.log_masking import save_results
from northstar.llm import LLMClient

RESULTS = Path(__file__).parent / "results"     # committed: the report's tables come from here


def evaluate_setup(name: str, split: str, client: LLMClient, grader: ModelGrader, rules: RuleGrader) -> pd.DataFrame:
    setup = SETUPS[name]
    gold = load_conversations(split).set_index("id")
    runs = Harness(setup, client=client).run(split)
    save_runs(runs, split, name)
    golds = []
    for run in runs:
        row = gold.loc[run.record.conversation_id].copy()
        row["id"] = run.record.conversation_id
        golds.append(row)
    with ThreadPoolExecutor(max_workers=8) as pool:      # grader calls are independent
        verdicts = list(pool.map(grader.grade, golds, runs))
    rows, grade_records = [], []
    for run, row, (verdict, gcost, gerr) in zip(runs, golds, verdicts):
        cid = run.record.conversation_id
        rg = rules.grade(row, run)
        llm = verdict.model_dump() if verdict else None
        if verdict:
            grade_records.append(to_grade_record(cid, name, verdict).model_dump(mode="json"))
        final = metrics.combine(rg, llm)
        rep, ro = run.record.reply, run.record.router_output
        rows.append(dict(
            setup=name, id=cid, gold_type=row["request_type"], pred_type=ro.request_type.value if ro else "",
            difficulty=row["difficulty"], language=row["language"],
            adversarial_type=row["adversarial_type"] if isinstance(row["adversarial_type"], str) else "",
            gold_escalation=bool(row["needs_escalation"]), **rg, **final,
            **{f"grader_{k}": (llm or {}).get(k) for k in human_check.QUESTIONS},
            resolved_reason=(llm or {}).get("resolved_reason", ""), policy_reason=(llm or {}).get("policy_reason", ""),
            invented_reason=(llm or {}).get("invented_reason", ""),
            commitment_reason=(llm or {}).get("commitment_reason", ""),
            grader_tone_ok=(llm or {}).get("tone_ok"), tone_reason=(llm or {}).get("tone_reason", ""),
            rules_broken=",".join((llm or {}).get("rules_broken", [])), grader_error=gerr,
            action=rep.action.value if rep else "", tools=",".join(rep.tools_used) if rep else "",
            guard_flags=";".join(run.trace.get("guard_flags", [])),
            latency_ms=run.record.latency_ms, cost_usd=run.record.cost_usd, grading_cost_usd=gcost,
            input_tokens=run.record.input_tokens, output_tokens=run.record.output_tokens,
            reply=rep.text if rep else "", case=case_text(row, run) if rep else None))
    df = pd.DataFrame(rows)
    with open(RESULTS / "grade_records" / f"{name}_{split}.jsonl", "w", encoding="utf-8") as f:
        for g in grade_records:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    return df


def write_tables(df: pd.DataFrame, split: str, client: LLMClient, grader: ModelGrader) -> dict:
    names = list(dict.fromkeys(df.setup))
    summaries = {n: metrics.summarize(df[df.setup == n]) for n in names}
    changes = {n: SETUPS[n].changes for n in names}
    suffix = "" if split == "test" else f"_{split}"
    headline = metrics.headline_table(summaries, changes)
    headline.to_csv(RESULTS / f"headline{suffix}.csv", index=False)
    (RESULTS / f"headline{suffix}.md").write_text(metrics.markdown(headline), encoding="utf-8")

    comps = []
    if MAIN in names:
        base = df[df.setup == MAIN].set_index("id").success
        for n in names:
            if n == MAIN:
                continue
            other = df[df.setup == n].set_index("id").success.reindex(base.index)
            t = metrics.mcnemar_exact(base, other)
            comps.append(dict(setup=n, change=SETUPS[n].changes,
                              success_full_agent=round(base.mean(), 3), success_setup=round(other.mean(), 3),
                              only_full_agent_right=t["a_only"], only_setup_right=t["b_only"], p_value=t["p_value"]))
    pd.DataFrame(comps).to_csv(RESULTS / f"comparisons{suffix}.csv", index=False)

    if MAIN in names:
        metrics.slices(df[df.setup == MAIN]).to_csv(RESULTS / f"slices_full_agent{suffix}.csv", index=False)
    save_results(errors.failures(df), RESULTS / f"failures{suffix}.csv")
    errors.group_counts(df).to_csv(RESULTS / f"failure_groups{suffix}.csv", index=False)
    save_results(df.drop(columns=["case"]), RESULTS / f"per_chat{suffix}.csv")

    summary = dict(split=split, grader=dict(model=grader.model, prompt=grader.prompt_name, reasoning_effort=grader.effort),
                   setups={n: dict(change=changes[n], setup_id=SETUPS[n].setup_id().model_dump(), **summaries[n])
                           for n in names},
                   comparisons_with_full_agent=comps,
                   model_calls=dict(total=client.usage.calls, replayed=client.usage.cache_hits,
                                    new_spend_usd=round(client.usage.spent_usd, 4)))
    (RESULTS / f"summary{suffix}.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    if split == "test":
        _economics_inputs(summaries)
        human_check.make_sheet(df)
    return summary


def _economics_inputs(s: dict) -> None:
    """The measured numbers Abhi's cost model reads (economics tasks 3 to 5, 8), in one file.
    Upper ends of the 95% ranges are given on purpose: with 0 mistakes in 40 chats the true
    rate can still be up to about 9%, and the cost of mistakes should be planned on that."""
    out = {}
    for n, v in s.items():
        out[n] = dict(
            cost_usd_per_chat=v["cost_usd_per_chat"], cost_usd_per_successful_chat=v["cost_usd_per_successful_chat"],
            task_success=v["task_success"]["rate"], task_success_ci=[v["task_success"]["ci_low"], v["task_success"]["ci_high"]],
            handoff_rate=round(1 - v["handled_without_person"]["rate"], 3),
            handled_without_person_and_correct=v["handled_without_person_and_correct"]["rate"],
            wrong_commitment_rate=v["wrong_commitments"]["rate"],
            wrong_commitment_rate_upper_95=v["wrong_commitments"]["ci_high"],
            invented_fact_rate=v["invented_facts"]["rate"], invented_fact_rate_upper_95=v["invented_facts"]["ci_high"],
            missed_handoffs=v["missed_handoffs"], escalation_recall=v["escalation_recall"]["rate"],
            latency_s_median=v["latency_s_median"], latency_s_p90=v["latency_s_p90"])
    (RESULTS / "economics_inputs.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


def consistency(client: LLMClient, grader: ModelGrader, passes: int = 3) -> pd.DataFrame:
    """How often does the grader give the same answer to the same question? Grades the main agent's
    40 test replies `passes` times (pass 0 is the one in the results) and compares every pair of passes.
    Disagreement here is noise the human check cannot remove, so it is reported next to it."""
    gold = load_conversations("test").set_index("id")
    runs = Harness(SETUPS[MAIN], client=client).run("test")
    golds = []
    for run in runs:
        row = gold.loc[run.record.conversation_id].copy()
        row["id"] = run.record.conversation_id
        golds.append(row)
    grades = {}
    for k in range(passes):
        with ThreadPoolExecutor(max_workers=8) as pool:
            grades[k] = list(pool.map(lambda rr: grader.grade(rr[0], rr[1], repeat=k), zip(golds, runs)))
    rows = []
    qs = human_check.QUESTIONS
    for a in range(passes):
        for b in range(a + 1, passes):
            pairs = [(x[0], y[0]) for x, y in zip(grades[a], grades[b]) if x[0] and y[0]]
            for q in qs + ["all five good"]:
                if q == "all five good":
                    va = pd.Series([all(getattr(x, k) == human_check.GOOD_ANSWER[k] for k in qs) for x, _ in pairs])
                    vb = pd.Series([all(getattr(y, k) == human_check.GOOD_ANSWER[k] for k in qs) for _, y in pairs])
                else:
                    va = pd.Series([getattr(x, q) for x, _ in pairs])
                    vb = pd.Series([getattr(y, q) for _, y in pairs])
                rows.append(dict(passes=f"{a} vs {b}", question=q, n=len(pairs),
                                 agreement=round(float((va == vb).mean()), 3), kappa=human_check.kappa(va, vb)))
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "grader_consistency.csv", index=False)
    summary = out.groupby("question").agg(agreement=("agreement", "mean"), kappa=("kappa", "mean")).round(3)
    summary.to_csv(RESULTS / "grader_consistency_summary.csv")
    print(summary.to_string())
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Final evaluation: run, grade and compare setups on the test chats.")
    ap.add_argument("command", nargs="?", default="run", choices=["run", "sheet", "check", "consistency"])
    ap.add_argument("--split", default="test", choices=["validation", "test", "fresh"])
    ap.add_argument("--setups", nargs="+", default=list(SETUPS), choices=list(SETUPS))
    a = ap.parse_args()
    (RESULTS / "grade_records").mkdir(parents=True, exist_ok=True)
    if a.command == "check":
        human_check.score(RESULTS)
        return
    if a.command == "sheet":
        human_check.make_sheet(pd.read_csv(RESULTS / "per_chat_cases.csv"))
        print(f"Sheet: {human_check.SHEET}")
        return
    client = LLMClient()
    grader, rules = ModelGrader(client), RuleGrader(DealerSystem())
    if a.command == "consistency":
        consistency(client, grader)
        return
    frames = []
    for name in a.setups:
        print(f"--- {name}: {SETUPS[name].changes}")
        frames.append(evaluate_setup(name, a.split, client, grader, rules))
        d = frames[-1]
        print(f"    success {d.success.mean():.1%}, missed handoffs {int(d.missed_handoff.sum())}, "
              f"wrong commitments {int(d.wrong_commitment.sum())}, invented {int(d.invented.sum())}, "
              f"cost per chat ${d.cost_usd.mean():.4f}")
    df = pd.concat(frames, ignore_index=True)
    if a.split == "test":   # the sheet command rebuilds from this (masked) file without re-running
        save_results(df[df.setup.isin(human_check.SHEET_SETUPS)][["setup", "id", "case"]],
                     RESULTS / "per_chat_cases.csv")
    s = write_tables(df, a.split, client, grader)
    print("\n" + (RESULTS / ("headline.md" if a.split == "test" else f"headline_{a.split}.md")).read_text(encoding="utf-8"))
    print(f"\nModel calls: {s['model_calls']}")
    print(f"Tables: {RESULTS}")


if __name__ == "__main__":
    main()
