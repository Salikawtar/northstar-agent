# Evaluation tasks tracker

> **Internal working file.** Decide whether to keep or remove it before the repository is shared with the evaluators.

**Main idea:** every task for Member 4 (experiments and evaluation, 14 marks), what it is, where it feeds into the project, and whether it is done. **Owner: Libo.** The development runs on the 30 validation chats (`docs/prompt_log.md`) are not the final evaluation: the 40 test chats are run once, at the end, with the agreed rubric.

Status values: **Done**, **Partly built**, **To do**.

| # | Task | What it is | Where it is used | Status |
|---|---|---|---|---|
| 1 | Success definition | Request resolved correctly, policy followed, right escalation, nothing invented (above all no coverage, price or loaner promised) | Report page 5; the rubric | Partly built: drafted in the project outline; measured in the development runs |
| 2 | Shared rubric | One grading rubric agreed by the team before the final test | Fair, repeatable grading (brief requirement) | To do |
| 3 | Evaluation harness | One command runs any setup on the 40 test chats and writes run and grade records | Report page 5; the README's single evaluation command | To do (`src/northstar/evaluation/`; contracts `RunRecord` and `GradeRecord` ready) |
| 4 | Rule-based grading | Checks a program can decide: route, escalation and queue, tools used, promises without a tool, verification | Accuracy, escalation quality, policy failures | Partly built: these checks already run in the pipeline, baseline and hand-written chat runs |
| 5 | Model grader | A model grades what rules cannot: invented facts, policy followed, reply quality | Hallucination and policy metrics | To do |
| 6 | Grader check | Model grader against the team's hand review of the 40 test chats: percent agreement and Cohen's kappa | Brief requirement ("validate against human judgments") | To do (hand-review labels exist, data task 7) |
| 7 | Same cases for every setup | The 40 test chats through: the three routers (with Neeraj), the full agent, the single-agent baseline | Report pages 4 and 5 | To do |
| 8 | One change at a time | Each comparison changes one thing: model, reasoning effort or prompt version | Controlled experiments (brief requirement) | Partly built: router runs on validation compared prompt v1/v2/v3, effort and model one at a time |
| 9 | Metrics | Task success, accuracy, latency, cost, policy failures, invented facts, escalation recall and precision | Headline results table | Partly built: all except invented facts and task success are measured in the development runs |
| 10 | Confidence ranges | 40 chats is small: show a range around each main rate | Honest results (outline promise) | To do |
| 11 | Error analysis | Group the errors, find the cause, propose or make a fix, re-test | Report page 5 | Partly built: development errors analysed and fixed (router mistakes, checker false alarms, verification gap) in `docs/prompt_log.md` |
| 12 | Results exports | Tables and failure examples saved to files, reproducible from recordings | Appendix; inputs for Abhi | To do |
| 13 | Hand results to the team | Final metrics and failure examples to Members 2, 3, 5 and 6 | Fine-tune comparison, guardrail rates, economics | To do |
| 14 | Report page 5 and appendix | Success criteria, method, held-out set, metrics, grader check, errors, fixes; full tables and rubric in the appendix | Final report | To do |

## Reminder before submission

- [ ] Decide whether to keep or remove this file before sharing the repository with the evaluators.
