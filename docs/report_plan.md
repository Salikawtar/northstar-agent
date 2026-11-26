# Final report: page plan, sources and consistency checks

**Main idea:** the report is 7 pages plus an appendix. Page 1 is the decision memo; pages 2 to 7 are the evidence, one grading criterion each (code quality is the repository itself, referenced on every page). Each page is condensed from one repository file, so every number has one source, and the economics numbers are checked by a test against the model output.

## Page budget

| Page | Content | Criterion (marks) | Source in the repository | Owner | Status |
|---|---|---|---|---|---|
| 1 | Decision memo: problem, recommendation, measured results, cost and benefit, risks, pilot gates | Economics and memo (20) | `docs/decision_memo.md` | Abhi (reference: Kawtar) | Ready |
| 2 | Synthetic data: design, personas, coverage, Faker, quality control with rejected and fixed examples, protected test set | Data (12) | `docs/data_quality.md`, `docs/generation_record.md`, `docs/data_dictionary.md` | Weidi | Draft from the source files |
| 3 | System design and agents: architecture diagram, router and three desks, tools and permissions, model and effort per component with the validation result behind it, edge cases, handoff, failure handling, prompt iteration | Design (12), agents and prompting (10) | `docs/architecture.md`, `docs/edge_cases.md`, `docs/prompt_log.md`, `docs/decision_log.md` | Kawtar | Draft from the source files |
| 4 | Fine-tuned router vs small and large prompted routers: accuracy, latency, cost, why it lost, volume where it pays, data-size study | Fine-tune (8) | `src/northstar/finetune/MODEL_CARD.md`, `src/northstar/finetune/README.md` | Neeraj | Draft written; LoRA sentence to add |
| 5 | Evaluation: success definition, 8 setups changing one thing each, ranges and paired tests, error analysis and fixes, grader checks | Evaluation (14) | `docs/evaluation_results.md`, `docs/evaluation_rubric.md` | Libo | Draft written (shared as a doc); grader check against people done (kappa 0.71 and 0.77) |
| 6 | Security and guardrails: policy P01 to P15, layers, red team 75 of 75, what still gets through | Security (12) | `docs/operating_policy.md`, `docs/guardrails.md` | Jessica | Draft from the source files |
| 7 | Economics: business case, unit economics, volumes, cost of mistakes, break-even, model trade-offs, uncertainty | Economics and memo (20) | `docs/economics.md` (sections 1 to 7) | Abhi (reference: Kawtar) | Ready |
| Appendix | Operating policy, key prompts, sample data, full results tables, economics assumptions and sensitivity | All | `docs/operating_policy.md`, `prompts/`, `data/conversations/` (sample rows), `src/northstar/evaluation/results/headline.md`, `docs/economics.md` (appendix A1 to A5), `src/northstar/economics/results/tables.md` | Assembler | Sources ready |

**Format:** 11 pt body text, normal margins. If a page runs over, cut words, never the font (keep every policy rule and every number with its range). Figures: architecture diagram (page 3), fine-tune comparison (page 4), economics cost-per-chat chart (page 7, `src/northstar/economics/results/cost_per_chat_vs_volume.png`).

## Consistency checks before submission

| Check | How |
|---|---|
| Economics numbers in the memo and page 7 match the model | `pytest tests/test_economics.py` (`test_memo_and_page7_quote_the_model`) |
| Evaluation numbers in the memo match page 5 | Memo table vs `src/northstar/evaluation/results/headline.md`: 70.0% (28/40), 52.5% blind, 18 of 18 handoffs, 1 of 40 wrong commitments and invented facts, 5.6 s median, 9.0 s p90 |
| Red-team and handoff numbers match page 6 | 75 of 75 resisted and handed to a person (`docs/guardrails.md`); 132 of 132 handoffs (`src/northstar/economics/results/summary.json`, `handoff_evidence`) |
| Fine-tune numbers match page 4 | 67.5% / 82.5% / 77.5% type accuracy; 249 ms vs 2,443 ms; break-even 197,000 chats (`src/northstar/finetune/results/`) |
| Every number reproduces | `python run_all.py` on a fresh clone (new environment from `requirements.txt`, no key). Afterwards `git status` may list a few result files: they differ only in latency (a replay re-measures a few milliseconds of local time), replay counters, line endings or a chart drawn again. No rate, cost or count changes, and `data/dms/` no longer changes |
| Model names and versions are the same everywhere | Claude Haiku 5.5 (router, booking desk), Claude Sonnet 5.5 (billing and warranty desks), GPT-6.2 Sol (grader), XLM-RoBERTa base (fine-tuned router), as in `config/settings.yaml` |
| No em dashes, no real personal data, no keys | Search the report text; the secrets check in `docs/guardrails_tasks.md` |
| Page count | 7 pages before the appendix |

## Reminder

- [ ] Decide whether to keep this file and the task trackers before sharing the repository with the evaluators.
