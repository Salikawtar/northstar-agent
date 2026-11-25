# Evaluation tasks tracker

> **Internal working file.** Decide whether to keep or remove it before the repository is shared with the evaluators.

**Main idea:** every task for Member 4 (experiments and evaluation, 14 marks), what it is, where it feeds into the project, and whether it is done. **Owner: Libo.** The development runs on the 30 validation chats (`docs/prompt_log.md`) are not the final evaluation: the 40 test chats are run once, at the end, with the agreed rubric.

Status values: **Done**, **Partly built**, **To do**.

| # | Task | What it is | Where it is used | Status |
|---|---|---|---|---|
| 1 | Success definition | Request resolved correctly, policy followed, right escalation, nothing invented (above all no coverage, price or loaner promised) | Report page 5; the rubric | Done: five questions, all must pass (`docs/evaluation_rubric.md`, D-31) |
| 2 | Shared rubric | One grading rubric agreed by the team before the final test | Fair, repeatable grading (brief requirement) | Done: v1.1 with decision rules and examples, used by the grader; agreed by all six members on 2026-11-25 |
| 3 | Evaluation harness | One command runs any setup on the 40 test chats and writes run and grade records | Report page 5; the README's single evaluation command | Done: `python -m northstar.evaluation` (or `python run_all.py evaluate`), replays in about 10 seconds, `RunRecord` and `GradeRecord` written |
| 4 | Rule-based grading | Checks a program can decide: route, escalation and queue, tools used, promises without a tool, verification | Accuracy, escalation quality, policy failures | Done: `src/northstar/evaluation/rules.py` (handoff, queue, unbacked promises, other people's data, data before verification, language, response-time claims) |
| 5 | Model grader | A model grades what rules cannot: invented facts, policy followed, reply quality | Hallucination and policy metrics | Done: GPT-6.2 Sol, blind to the setup, tool results shown (`prompts/grader/evaluation_v3.md`); developed on validation only (v1 to v3, `docs/prompt_log.md`) |
| 6 | Grader check | Model grader against the team's hand review of the 40 test chats: percent agreement and Cohen's kappa | Brief requirement ("validate against human judgments") | Done: Libo and Jessica labelled 80 blind replies; overall kappa 0.71 and 0.77 (target 0.6), handoffs 100% agreement; the grader rates the main agent 7.5 points higher and the single agent 10 to 15 points lower than people (`docs/evaluation_results.md` 5.3) |
| 7 | Same cases for every setup | The 40 test chats through: the three routers (with Neeraj), the full agent, the single-agent baseline | Report pages 4 and 5 | Done: 8 setups on the same 40 chats (`results/headline.md`) |
| 8 | One change at a time | Each comparison changes one thing: model, reasoning effort or prompt version | Controlled experiments (brief requirement) | Done: router model (Sonnet, fine-tuned), router prompt (v2), warranty effort (high), checks off, architecture, fixes off; exact McNemar tests (`results/comparisons.csv`) |
| 9 | Metrics | Task success, accuracy, latency, cost, policy failures, invented facts, escalation recall and precision | Headline results table | Done: plus containment, cost per successful chat and tone, each tied to a business outcome (`metrics.py`) |
| 10 | Confidence ranges | 40 chats is small: show a range around each main rate | Honest results (outline promise) | Done: 95% Wilson intervals on every rate, bootstrap range on median latency |
| 11 | Error analysis | Group the errors, find the cause, propose or make a fix, re-test | Report page 5 | Done: 19 blind failures in 9 groups; 4 fixed in code (D-32), re-tested on test, validation, hand-written chats and red team; 1 side effect and 5 proposals reported (`docs/evaluation_results.md`) |
| 12 | Results exports | Tables and failure examples saved to files, reproducible from recordings | Appendix; inputs for Abhi | Done: `src/northstar/evaluation/results/` (headline, comparisons, slices, failures, failure groups, per chat, grade records, economics inputs) |
| 13 | Hand results to the team | Final metrics and failure examples to Members 2, 3, 5 and 6 | Fine-tune comparison, guardrail rates, economics | Done in the repository: section 7 of `docs/evaluation_results.md` and `results/economics_inputs.json`; to send to the team |
| 14 | Report page 5 and appendix | Success criteria, method, held-out set, metrics, grader check, errors, fixes; full tables and rubric in the appendix | Final report | Draft written (shared as a doc), grader-check numbers included |

**Headline (40 test chats, recommended agent):** 70% task success (55 to 82), 18 of 18 needed handoffs made, 1 wrong commitment, 1 invented fact, 5.6 s median wait, $5.34 per 1,000 chats. The blind run before the fixes: 52.5%.

## Reminder before submission

- [ ] Decide whether to keep or remove this file before sharing the repository with the evaluators.
