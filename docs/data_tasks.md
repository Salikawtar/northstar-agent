# Data tasks tracker

> **Internal working file.** Decide whether to keep or remove it before the repository is shared with the evaluators.

**Main idea:** every task related to the synthetic data, what it is, where the data is used later in the project, who owns it, and whether it is done. The current dataset version is **v1113** (`data/source/northstar_synthetic_dataset_v1113.xlsx`, 2026-11-11).

Status values: **Done**, **Decided** (agreed, not yet applied), **To do**, **Optional**.

| # | Task | What it is | Where the data is used | Owner | Status |
|---|---|---|---|---|---|
| 1 | Coverage plan | Target counts per request type, difficulty, persona and language (20 per type; 10 easy / 6 hard / 4 adversarial; 13 EN / 7 FR) | Report page 2 (composition table); keeps fine-tune labels balanced | Weidi | Done |
| 2 | 200 conversations | Three-turn chats with Faker names, emails, VINs, plates and repair orders | Fine-tune training (Neeraj), agent testing (Libo), mock dealer system build (Kawtar) | Weidi | Done |
| 3 | Balance warranty fraud | Raised from 5 to 8 chats so all 5 attack types have 8 | Adversarial coverage in the data section; escalation labels for the fine-tune | Claude | Done |
| 4 | Quality check pass | Fixed 28 agent replies that promised coverage or refunds, 14 incoherent chats, 183 em dashes; every change logged in QC_log | Report page 2 and appendix (examples of what was fixed) | Claude | Done |
| 5 | Train / test split | 160 train / 40 test, grouped by customer, no near-copies across the split, 1 PII case added to test | Held-out test for accuracy, latency and cost (Libo, Neeraj) | Claude | Done |
| 6 | Red-team set | 75 attacks, 15 per attack type, 3 tactics each; drafted, then rewritten by hand by the team | Guardrail pass rates per attack type (Jessica), report page 6 | Claude + team | Done |
| 7 | Hand review | 74 chats (40 test + rewritten rows) and 75 attacks marked keep / fix / reject | "Reviewed by hand" evidence for criterion 1; grader check against human labels (Libo) | Team | Done |
| 8 | Merge team fixes | 22 chat fixes and 75 rewrites merged into v1111, plus the v3_0124 consistency fix | Final dataset used by every module | Claude | Done |
| 9 | Escalation rule | `needs_escalation` = True for safety (roadside), bereavement and legal threats (needs_human), all adversarial attempts, explicit requests for a manager, and billing disputes that contest a charge (86 of 200; disputes added 2026-11-11, D-13) | Fine-tune label (Neeraj), handoff rules (Kawtar), escalation recall metric (Libo), human-review cost (Abhi) | Kawtar | Done |
| 10 | Branch names | Add the 8 branches mentioned in chats (Scarborough, Vaughan, Brampton, Etobicoke, Markham, Burlington, Richmond Hill, Ajax) to the mock dealer system | Dealer system settings, so the agent never denies a branch a test chat mentions | Kawtar + Weidi | Done |
| 11 | Red-team dealer records | 40 customers, vehicles and repair orders so attackers pass identity checks and reach the guardrails | Mock dealer system; guardrail tests (Jessica) | Claude | Done |
| 12 | Generation record | Models, temperature, prompt version and rejected rows with reasons from the original generation | Report page 2 and appendix (criterion 1 asks for documented generation and rejects) | Weidi | To do |
| 13 | Generation script in repo | A runnable data-generation pipeline (the brief requires it in the codebase) | GitHub submission; reproducibility (criterion 3) | Weidi or Kawtar | To do |
| 14 | Validation split | 30 rows moved from train, grouped by customer: 130 / 30 / 40 | Fine-tune tuning and early stopping (Neeraj) | Kawtar | Done |
| 15 | Export to repo | v1112 saved as CSV/JSON in `data/` (original xlsx replaced); loaded through `src/northstar/data.py` | Loaded in code by fine-tune, evaluation and guardrail modules | Kawtar | Done |
| 16 | Load into dealer system | Add the red-team records (task 11) and branches (task 10), re-run `python run_all.py dms` and the tests | Agent tools and verification; guardrail tests | Kawtar | Done |
| 17 | Update docs | Data dictionary and README: splits, red-team set, escalation rule | Newcomer-friendly README (criterion 3); team hand-off | Kawtar | Done |
| 18 | Fix past dates | Move booking dates that fall before the mock "today" (2026-11-16), e.g. v3_0038 | Realism; prevents fake agent errors in evaluation | Kawtar | Done |
| 19 | Hand-written test chats | About 20 tricky chats written fully by the team (multi-intent, conflicting details, incomplete messages) | Test set "written by hand" (criterion 1); edge-case tests (criterion 7) | Team | Optional |
| 20 | Report data section | Page 2 plus appendix: composition table, fixed and rejected examples, limits (word-overlap duplicate check, chat only, single-message attacks) | Final report | Weidi | To do |

## Reminder before submission

- [ ] Decide whether to keep or remove this file before sharing the repository with the evaluators.
