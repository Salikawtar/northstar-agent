# Evaluation protocol (draft v1, 2026-11-25)

**Status:** draft, waiting for Neeraj to confirm the items in section 12. Once confirmed, this file is frozen: any later change gets a dated line in section 13 saying what changed and why.

**Purpose:** one set of rules so that the fine-tuned router, its variants, the prompted LLMs (Haiku, Sonnet, others) and Jev are all compared on the same chats, the same inputs, the same outputs and the same scoring, and so that nothing is chosen using the test chats. The rules are written before any new results exist, so they cannot be bent to fit them.

The code that enforces these rules is `src/northstar/finetune/protocol.py` (labels, inputs, seeds, folds, the test lock) and `make_folds.py` (the folds).

## 1. Data

- File: `data/conversations/conversations.csv`, the team's dataset (v1114). Its SHA-256 is checked on every load; a different file is refused. Provenance: `data/README.md`.
- 200 chats: 130 train, 30 validation, 40 test, grouped by customer (99 customers).
- **Pool = train + validation = 160 chats.** Everything (training, selection, thresholds, calibration, prompt and schema tuning for baselines) uses only the pool.
- **Test = 40 chats, locked.** `pool()` never returns them. `test_set()` refuses to open them unless the caller passes `final=True` and the environment variable `NORTHSTAR_ALLOW_TEST=1` is set; every opening is appended to `outputs/test_access.log`. The test chats are scored once, in the final step (section 11).
- Known limits: all chats come from one generator (Claude), and 126 of 200 were not human-reviewed (all 40 test chats were). A fresh held-out set from a different generator is planned for the end (action plan A3).

## 2. Folds

- 5-fold cross-validation on the 160-chat pool, **grouped by `customer_id`** (all chats of one customer stay in one fold) and **stratified by `request_type`**.
- The fold assignment is made once and saved in `data/folds/folds_v1.csv` (with `folds_v1.meta.json`). Every machine reads the saved file; nobody redraws folds, because scikit-learn gives different folds on different versions.
- Three repeats are saved (`rep0`, `rep1`, `rep2`). `rep0` is the default. The others are used only for a repeated-CV check on the finalists.
- Because grouping by customer leaves only 79 units to place, random splits come out lopsided (a first attempt had 4 French chats in one fold and 15 in another). So customers are assigned to folds by a small simulated-annealing search (numpy only, fixed seeds 894, 895, 896) that keeps every fold close to the overall mix of request types, escalation rate, adversarial rate, French share and size, and never leaves a fold without a request type. The search uses labels only, never model results, and does not depend on the scikit-learn version.
- The folds are drawn by running `make_folds.py` in the first Kaggle notebook (`notebooks/01_protocol_and_folds.ipynb`); the resulting `data/folds/folds_v1.csv` is committed and never redrawn.
- Limit: chats from different customers can still be near-duplicates (the team found one similar towing pair). They are not grouped.

## 3. Outputs every router must produce

| Output | Values | Notes |
|---|---|---|
| Request type | 10 labels, same order as `contracts.py` | |
| Escalation | yes / no | |
| Reason | none, safety, bereavement, legal_threat, adversarial, customer_request, policy_limit | **Not trained as a seven-way answer** (decision 2026-11-25): the dataset has no reason column, and labels written afterwards would be invented. **Scored by where it sends the chat** (updated 2026-11-26): the team's grader decides the acceptable team from two dataset columns, `request_type` and `adversarial_type` (`evaluation/rules.py`, copied in `routing.py`), so the right-team rate is measured with real labels for every router. A tuned router gets its reason from type + attack (a fixed rule) or from a language-model step. |
| Attack | yes / no | Added 2026-11-26. A real label: `adversarial_type` is non-empty (40 chats, all need a person), the same definition the team's grader uses. Read from the chat text only; the column is the answer learned, never an input. |
| Language | en / fr | By the word rule (`routing.language_rule`, decision 2026-11-26): as accurate as a language head and cannot affect the other answers. |

Consistency rule: escalation is yes if and only if the reason is not "none". Enforced in code for every router, so a router cannot say "escalate" with reason "none".

## 4. Input variants

Every router is compared on all three, on the same chats:

| Variant | Text | Why |
|---|---|---|
| `first_message` | the customer's first message | what a router sees in production |
| `customer_turns` | first and last customer messages | what the original notebook used |
| `full_conversation` | customer, agent, customer, formatted as the team's prompted router formats it | what the team's pipeline currently passes |

**Primary-variant rule (decided in advance):** the primary variant is `first_message` if its cross-validated macro-F1 is within one seed-to-seed standard deviation of the best variant; otherwise the best variant is primary, and the report says the production-realistic input costs accuracy. All three are always reported.

## 5. Seeds

- Cross-validation training seeds: 11, 22, 33.
- Final training seeds: 101, 102, 103, 104, 105.
- Every training run sets the seed for Python, NumPy, PyTorch and the data-loader shuffle.

### Epoch count and training recipe (added with notebook 02)

- Step 2 reproduces the original recipe: XLM-RoBERTa base, learning rate 2e-5, batch 16, constant learning rate, no warmup, no gradient clipping, up to 30 epochs. Chats are padded per batch and the arithmetic runs in half precision (faster; no change expected beyond noise). Chats are cut at 320 tokens, which no chat reaches.
- Every run scores its held-out fold after every epoch. **One** epoch count (E*) is then chosen for all runs: the best point of the mean held-out macro-F1 curve over variants and seeds, smoothed over three neighbouring epochs. This is chosen on the same folds it is scored on, so cross-validation scores are very slightly optimistic; the test chats are untouched.
- Recipe changes (warmup and decay, clipping, LoRA) are separate experiments in step 6, compared on the same folds and seeds.

## 6. Metrics

| Output | Primary | Also reported |
|---|---|---|
| Type | macro-F1 | accuracy, per-class recall, confusion pairs, English vs French |
| Escalation | F2 (recall counts twice as much as precision) | recall, precision, accuracy, missed escalations (count) |
| Reason | right-team rate: chats needing a person that reach a team the grader accepts, out of all chats needing a person (a missed handoff counts as wrong) | attacks sent to the right team; wrong-team count; extra handoffs |
| Attack | F2 | recall, precision |
| Whole handoff decision | handled right (strict): share of chats fully right: a person and an acceptable team when one is needed; when not, the AI keeps the chat and the right desk answers it | the same without the desk check ("rule checks only", as the team's rule checks); kept with the wrong desk |
| Language | accuracy | |
| Confidence | expected calibration error (10 equal-width bins) | Brier score, reliability table |
| System | cost per chat, median and p90 latency | parameters, memory |

- Escalation threshold: chosen on the out-of-fold predictions of the pool by maximising F2, never on the test chats.
- Cross-validation results are reported as mean and standard deviation over folds and seeds, and as the pooled out-of-fold prediction for every chat.
- With 160 chats, differences smaller than the seed-to-seed standard deviation are called "not distinguishable".

## 7. Selection rules (fixed before results)

- Type models: highest cross-validated mean macro-F1. Ties (within one seed-to-seed standard deviation) go to the simpler, cheaper, faster option.
- Escalation head: highest cross-validated mean F2 at the threshold chosen above.
- Nothing is chosen using the test chats, including the cascade threshold and trigger rules.
- Router choice (added 2026-11-26): safety first (missed handoffs, handoffs to the right team, attacks to the right team), then efficiency (extra handoffs, chats kept with the wrong desk); strict handled-right summarises both. A safety measure is never traded for efficiency.
- Unsure line for a tuned router (added 2026-11-26): the team's pipeline hands a chat to a person below a confidence line (0.55, set for Haiku). For a tuned router the line is chosen on the pool from 0.55, 0.50, ..., 0.20, 0: the best strict handled-right that never misses more handoffs than 0.55 does; ties go to the higher line (`router_options.choose_floor`).

## 8. Uncertainty and comparisons

- 95% intervals by bootstrap over customers (resampling customers, not chats), so a customer's chats stay together.
- Two methods on the same chats are compared with an exact McNemar test on paired right/wrong, plus the mean paired difference with its interval.
- Every comparison run is listed in the report, not only the ones that came out well.

## 9. Rules for baselines (apples to apples)

Applies to Haiku, Sonnet, any other LLM and Jev.

- Same chats, same input variant, same label lists, same pool-only tuning budget. The number of prompt or schema iterations tried is recorded for every baseline, including the fine-tuned model's configurations.
- Schema (changed 2026-11-25, before any baseline was run): Haiku and Sonnet get the team's router prompt v3 unchanged (`prompts/router_v3.md`), so they are measured exactly as the team's system runs them. Its JSON also carries a reason and secondary types; those are saved, not scored. Every router is scored on the same three answers: type, escalation, language. No separate narrow-schema prompt is written: it would be a new, untuned prompt, and the reason is parked. Jev gets typed questions built from the same prompt wording (one version, not tuned).
- At least three repeated runs per baseline to measure run-to-run variation; model name, version, temperature and reasoning effort are recorded. Raw outputs are cached per chat.
- The team's prompts were tuned on the 30 validation chats, which are part of the pool, so baseline scores on the pool are optimistic. The clean comparison is on the test chats and later on the fresh held-out set.
- Latency: batch size 1, fixed hardware stated in the report (CPU for the fine-tuned model; the API round trip for LLMs), warm-up call excluded, median and p90. For the API models on the pool: the first 40 pool chats, one call at a time (the accuracy runs send six calls at once to save time, which can slow each call).
- Cost: measured tokens at the provider's listed prices on the run date; fine-tuned cost includes the server assumptions stated in the economics scenarios.

## 10. Cascade and system tests

- The cascade (fine-tuned model first, an LLM for hard cases) is evaluated on out-of-fold predictions; its threshold and triggers are chosen on the pool.
- The integration test (the router inside the team's full agent) is labelled as a deployability test, and uses the same reason step for every router.

## 11. Final run (once)

1. Freeze configurations and thresholds from the pool.
2. Train the chosen configurations on all 160 chats with the five final seeds.
3. Open the test chats once (`NORTHSTAR_ALLOW_TEST=1`, `final=True`, with a note), score every method, and report intervals and paired tests.
4. After this, no change to the models or the rules is allowed without a new fresh held-out set.
5. As run (decided 2026-11-26, before opening): the settings are frozen in `config/final_settings.json`; two fine-tuned setups are scored ("safest" and "balanced", see that file for why); the team's fresh held-out set (31 chats, `protocol.fresh_set`, locked like the test chats) is scored alongside the 40 test chats; Haiku, Sonnet and Jev (both versions) run on both sets with the same code. Notebook `06_final_run.ipynb`.

## 12. To confirm (Neeraj)

1. Primary-variant rule in section 4.
2. Primary metrics in section 6, in particular F2 for escalation and macro-F1 for type and reason.
3. Seeds in section 5, and 5 folds with 3 saved repeats.
4. 95% intervals by customer bootstrap and exact McNemar in section 8.
5. The baseline rules in section 9, in particular the pool-only tuning budget and at least three repeated LLM runs.

## 13. Changelog

- 2026-11-25: draft v1 written.
- 2026-11-25: fold method changed from random stratified-group draws to a balancing search (first draw was too lopsided on language). Folds are produced on Kaggle and committed.
- 2026-11-25: section 9, before any baseline run: one schema (the team's prompt unchanged, three answers scored) instead of two; API latency from 40 sequential calls.
- 2026-11-26, after a first look at the attack-head results on the pool (test chats untouched): strict handled-right (desk checked) replaces the rule-checks-only version as the main summary, both reported; safety-first router choice and the unsure-line rule added to section 7.
- 2026-11-26, after the team's end-to-end result (its fine-tuned router lost on handoff teams) and before any of our routers was scored this way: the reason is scored by the right-team rate with the grader's own rule; an attack yes/no output is added (real label); language comes from the word rule. Router options compared on the pool: tuned alone (type rule or attack answer), tuned + language-model reason step, plus cascade, and language model alone.
