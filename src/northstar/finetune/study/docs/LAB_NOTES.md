# Lab notes

A running log of what was done, what came out, and what was decided. Newest entry last. Every number here points to a saved result file or a notebook cell; none is typed in from memory.

Entry format: **date, step** | what we did | what came out | decision | next.

---

## 2026-11-25, Step 1: repo check
- **What:** read the repo, the training script and the laptop's setup.
- **Came out:** repo clean and in sync with GitHub; `train_router.py` scores the test chats on every run, has no cross-validation, reads only `customer_text`, saves only summary numbers. The laptop (7.9 GB RAM, 2-core i3, no GPU) cannot train; all compute goes to Kaggle.
- **Decision:** build on this repo (own git), share with Kawtar for integration later. Kaggle for all compute, laptop for editing only.

## 2026-11-25, dataset
- **What:** compared the notebook's `conversations_fixed.csv` with the team's `conversations.csv`.
- **Came out:** same 200 chats, splits and text; three billing-dispute escalation labels differ (v3_0027 test; v3_0110 and v3_0171 train). The team file follows the team's rule of 2026-11-11 (a question about a charge is answered, not escalated).
- **Decision:** use the team file everywhere. Copied unchanged to `data/conversations/conversations.csv` with provenance in `data/README.md` (SHA-256 checked on every load).

## 2026-11-25, Step 2: evaluation protocol (draft)
- **What:** wrote `docs/EVAL_PROTOCOL.md` and `src/northstar/finetune/protocol.py` (labels, three input variants, seeds, dataset hash check, saved folds, test lock).
- **Came out:** a random grouped split of the 160-chat pool was lopsided (one fold had 4 French chats, another 15) because only 79 customers can be placed.
- **Decision:** assign customers to folds with a balancing search (`make_folds.py`, numpy only, fixed seeds), run it once on Kaggle, commit `data/folds/folds_v1.csv` and never redraw it.
- **Next:** run `notebooks/01_protocol_and_folds.ipynb` on Kaggle, bring the folds back, then Neeraj confirms the five items at the end of the protocol.

## 2026-11-25, Step 1 result: folds
- **What:** ran `notebooks/01_protocol_and_folds.ipynb` on Kaggle; brought `folds_v1.csv`, its meta file, the balance table and chart into `data/folds/` and `results/step01/`.
- **Came out:** checked on the laptop: 160 chats, no customer split across folds in any of the three repeats, every fold has 32 chats, 13 to 14 chats that need a person, 11 to 12 French chats, and 3 to 4 chats of every request type. The three repeats are genuinely different splits (partition agreement near zero), even though they report the same objective value (the same best balance).
- **Decision:** `rep0` is the default fold set; `rep1` and `rep2` are kept for a repeated-CV check on the finalists.

## 2026-11-25, Step 2 build: CV harness and input comparison (not yet run)
- **What:** wrote `model.py` (shared encoder plus configurable heads), `train_cv.py` (cross-validated training that saves every held-out chat's raw scores at every epoch), `cv_analysis.py` and `metrics.py` (CPU-only analysis, scoring, customer-level bootstrap, exact McNemar), and `notebooks/02_cv_baseline_and_inputs.ipynb`.
- **Checked here:** all code parses; the analysis, plotting and test code ran end to end on synthetic saved runs (numbers meaningless, only the plumbing was tested); an incomplete CV is refused.
- **Not checked here:** real training (no GPU on the laptop). The notebook starts with a one-fold, two-epoch smoke test and a time estimate before the long run.
- **Bug found and fixed before the first Kaggle run:** a tiny test with a toy encoder showed that PyTorch refuses a head named `type` (`KeyError: attribute 'type' already exists`), which would have crashed the first run. Heads are now stored under `head_type`, `head_escalation`, and so on, and the plain names are restored in the model's output. The test environment was deleted afterwards; from now on all model code is run only on Kaggle.
- **Expected cost:** the original notebook took about 215 s per 30-epoch run on Kaggle; 3 inputs x 3 seeds x 5 folds = 45 runs, so the unoptimised cost would be about 2.7 hours. Per-batch padding and half precision should cut that substantially; the smoke test will measure it.
- **Next:** push, run on Kaggle with the GPU on, bring back `results_02.zip`.

## 2026-11-25, Step 2 result: cross-validated baseline and input comparison
- **What:** ran `notebooks/02_cv_baseline_and_inputs.ipynb` on a Kaggle T4 (commit `313227b`): original recipe, 3 inputs x 3 seeds x 5 folds = 45 runs, about 45 minutes (52 s, 58 s and 71 s per run for first message, customer turns and full conversation). Raw scores are in `results/cv_old_recipe/` (the 45 runs plus a config file per input); tables and figures are in `results/step02/`.
- **Came out (160 out-of-fold chats, epoch 29, mean over 3 seeds; see `results/step02/cv_summary.csv`):**
  - Type accuracy: first message 0.72, customer turns 0.70, full conversation 0.75. Averaging the 3 seeds gives 0.76, 0.74 and 0.78, so a seed ensemble is worth 3 to 5 points.
  - 95% intervals (resampling customers) are about 0.69 to 0.82, 0.68 to 0.81 and 0.70 to 0.85; every pairwise exact McNemar test has p above 0.45. **No input is measurably better than another.**
  - Seed-to-seed spread of the pooled score is only 1 to 3 points (the original notebook's 5.5-point spread was on 40 chats).
  - Escalation at the default threshold: recall about 0.75 (about 17 of the 69 chats that need a person missed), precision about 0.86, F2 about 0.77.
  - First-message input, per request type: best roadside (0.94), worst needs_human (0.56), repair_status and out_of_scope (0.69). English 0.82 vs French 0.64 (104 vs 56 chats).
- **Learning curves:** held-out macro-F1 is near zero for the first 5 epochs, climbs from epoch 7 to 17, then plateaus from about epoch 18 to 30. Held-out loss flattens near epoch 18 and does not rise; training loss keeps falling to about 0.1.
- **Decisions:**
  - Primary input by the pre-written rule: **first message** (it is 0.028 macro-F1 behind the best input, inside the 0.036 seed-to-seed spread). So the production-realistic input costs no measurable accuracy.
  - E* = 29 by the rule, but the plateau starts near epoch 18, so the exact choice inside 18 to 30 is noise. Keep 30 for the original recipe.
- **Reading and limits:** the first 15 epochs are largely spent getting started (constant learning rate 2e-5, no warmup, only 8 steps per epoch), which points to a recipe change (warmup and decay, higher learning rate) as a cheap speed-up and possibly a gain. The escalation recall and the French gap are the visible weaknesses. All differences between inputs are inside the noise at 160 chats.
- **Next:** one Kaggle notebook on the first-message input that tests (a) a language head, (b) a warmup-and-decay recipe, and (c) the escalation threshold chosen on out-of-fold scores; then gold labels for the escalation reasons.

## 2026-11-25, Track C: draft reason labels
- **What:** gave all 200 chats an escalation reason in a separate file, `data/labels/escalation_reasons.csv` (the dataset itself is untouched). Rules derived 169 rows: 113 none, 40 adversarial, 16 safety (roadside), 13 policy_limit (contested charge). I read the remaining 18 escalating chats by hand (16 needs_human, 2 warranty_claim) and drafted a reason, a confidence and a note for each.
- **Came out:** overall counts none 113, adversarial 40, safety 25, policy_limit 14, legal_threat 3, customer_request 3, bereavement 2. Half the drafted rows (9 of 18) are medium confidence, with the alternative named in the note. Rare reasons have 2 to 3 chats each, and the 40 test chats hold only 1 bereavement, 1 customer_request and no legal_threat.
- **Status:** draft, waiting for Neeraj's approval of the 18 drafted rows. Definitions follow the team's router prompt v3.
- **Decision (same day):** Neeraj parked this. The dataset has no reason column, so labels written afterwards would be invented ground truth; the tuned model is not trained or scored on reasons for now. The file stays as a parked draft (`data/labels/README.md` says so) and is not committed. Reason handling returns later via the data owner or a language-model fallback.
- **Next:** notebook 03 adds the language head and LoRA only.

## 2026-11-25, Step 3 build: language head and LoRA (not yet run)
- **What:** added LoRA to `model.py` (freeze the pretrained weights, train small add-on matrices on the attention query and value layers, rank 8, alpha 16) and `train_cv.py` (config switch, optimiser over trainable weights only, trainable-parameter count and run time saved per run); `cv_analysis.py` now scores a language head; wrote `notebooks/03_language_head_and_lora.ipynb`.
- **Models compared on the same folds, first-message input, 3 seeds:** the notebook-02 baseline (read from `results/cv_old_recipe`), the same model plus a language head, and LoRA with the language head at learning rates 1e-4 and 3e-4 (LoRA normally needs a bigger step than full fine-tuning, so two values are tried).
- **Checked here:** all code parses; the analysis cells ran end to end on synthetic runs (plumbing only). LoRA and the language head have not been run on real data; the notebook starts with a smoke test of all three models.
- **Dependency:** the notebook needs `results/cv_old_recipe` and the new code on GitHub, so push first.
- **Housekeeping:** `data/labels/` (the parked draft reason labels) is in `.gitignore` so it cannot be committed by accident.

## 2026-11-25, Kaggle setup lessons
- **What happened:** the first Kaggle run failed with `cannot import name 'protocol'`. Two causes: (1) the new files had not been pushed to GitHub yet, and (2) after the push, Kaggle still held the old clone from the first run, because the notebook only cloned when the folder did not exist.
- **Also found:** on Windows, git rewrote the dataset's line endings when staging it, which would have broken the SHA-256 check on Kaggle's Linux machine. `.gitattributes` now keeps `conversations.csv` byte-for-byte.
- **Decision:** the first cell of every Kaggle notebook deletes any old copy and clones fresh, clears stale imports, and stops with a clear message if the code is missing. Rule for later steps: push first, then run on Kaggle.

## 2026-11-25, Step 3 run: library clash on Kaggle
- **What happened:** the smoke test stopped when LoRA was switched on: `ImportError: Found an incompatible version of torchao. Found version 0.10.0, but only versions above 0.16.0 are supported`. The newest `peft` checks for an optional speed-up library (`torchao`) while adding the LoRA pieces, and Kaggle's image carries an old copy of it. We do not use `torchao`.
- **Fix:** the first cell now removes `torchao` (`pip uninstall -y torchao`) right after installing `peft`, before anything is imported. In a session that has already imported the libraries, restart the session after the uninstall.

## 2026-11-25, Step 4 build: comparison models (not yet run)
- **What:** `baselines.py` (calls through OpenRouter with retries, a spending limit and a cache of every answer) and `notebooks/04_baselines_haiku_sonnet_jev.ipynb`. Haiku 5.5 and Sonnet 5.5 get the team's router prompt v3 unchanged (copied to `prompts/router_v3.md`, provenance in `prompts/README.md`) and the team's settings (reasoning effort low, 1500 output tokens, no temperature, one correction call, then the team's fail-safe). Jev 1.14 gets four typed questions (type, escalation, language, and the reason as an unscored extra) built from the same prompt wording. All three see the 160 pool chats with the first-message and full-conversation inputs; Haiku and Sonnet 3 repeats, Jev 2.
- **Jev's call format** was taken from OpenRouter's Decisions documentation (`POST /api/alpha/decisions`, typed questions, an answer and probabilities per question). Not yet confirmed by a real call: the notebook prints Jev's raw reply on the first chat and stops if it is not in that shape.
- **Checked here (no network, fake answers):** prompt parsing, answer parsing (good, malformed, refused), resume and replay from the cache, a run of mostly unusable answers is refused instead of saved, a key or credit error stops the run, and the notebook's scoring cells run end to end. The tuned-model rows reproduce notebook 02 (first message: 0.719 single run, 0.756 combined).
- **Expected cost:** about $6 (mostly Sonnet), hard stop at $10. Runs on a CPU notebook, so it can run while notebook 03 trains.
- **Protocol change (before any baseline result):** one schema instead of two; see EVAL_PROTOCOL section 9 and its changelog.

## 2026-11-25, Step 3 result: language head and LoRA
- **What:** ran `notebooks/03_language_head_and_lora.ipynb` on a Kaggle T4 (commit `15fddb8`, with the `torchao` line added by hand in Kaggle): 3 new models x 3 seeds x 5 folds = 45 runs, first-message input, 30 epochs. Raw scores in `results/cv_step03/` (45 runs and a config per model; all record commit `15fddb8`, Tesla T4, the team dataset); tables, figure and the executed notebook in `results/step03/`.
- **Came out (160 out-of-fold chats, each model at its own best epoch, mean ± sd over 3 seeds; `results/step03/cv_summary_step03.csv`):**

  | Model | Epoch | Type accuracy | Type macro-F1 | Escalation recall | Escalation precision | Language | Combined type acc [95% CI] | Trained numbers | s per run |
  |---|---|---|---|---|---|---|---|---|---|
  | baseline (notebook 02) | 27 | 0.721 ± 0.043 | 0.722 ± 0.043 | 0.715 ± 0.017 | 0.857 ± 0.032 | no head | 0.788 [0.72, 0.86] | 278 million | 52 |
  | full_3heads | 30 | 0.700 ± 0.051 | 0.699 ± 0.048 | 0.734 ± 0.059 | 0.868 ± 0.016 | 1.000 | 0.744 [0.67, 0.82] | 278,053,645 | 54 |
  | lora_1e4 | 30 | 0.260 ± 0.016 | 0.226 ± 0.014 | 0.377 ± 0.091 | 0.616 ± 0.019 | 0.992 | 0.275 [0.21, 0.34] | 304,909 | 27 |
  | lora_3e4 | 30 | 0.638 ± 0.044 | 0.635 ± 0.042 | 0.720 ± 0.008 | 0.774 ± 0.057 | 0.998 | 0.688 [0.61, 0.76] | 304,909 | 27 |

  (The baseline's 52 s per run is from notebook 02. Its best epoch is 27 here because the rule is applied to the first-message runs alone; notebook 02 applied it to all three inputs together and got 29.)
- **Paired tests against the baseline** (combined answers, exact McNemar; `comparisons_step03.csv`): full_3heads right on 3 chats the baseline missed, baseline right on 10 it missed, p = 0.092; lora_3e4 8 vs 24, p = 0.007; lora_1e4 4 vs 86, p < 0.001.
- **Language** (`language_accuracy.csv`, combined answers): full_3heads and lora_3e4 1.000 on both English (104) and French (56); lora_1e4 0.988 (misses 2 English chats) although it gets only 26% of request types right.
- **Learning curves** (`learning_curves.png`): full fine-tuning rises from epoch 7 and plateaus from about epoch 18, as in notebook 02; full_3heads sits slightly below the baseline from about epoch 10 on. LoRA at 3e-4 is still climbing steeply at epoch 30 (under-trained in this budget); LoRA at 1e-4 barely learns.
- **Reading:**
  - Language is easy in this data: every model gets it, even one that has not learned the request types. The language head adds nothing over the simple word rule (100% in an earlier check) and leans against request type (10 vs 3 chats, p = 0.09, not significant).
  - LoRA loses clearly under this budget, and it is not steadier (sd 0.044 vs 0.051). It trains 0.11% of the numbers (the notebook text first said "about 1%", which was wrong; corrected) and halves training time, which does not matter at 54 s per run; at run time it is as fast as the full model.
- **Decision:** pending (Neeraj): language from the third head or from the word rule; whether to give LoRA one more learning rate (1e-3) before reporting it as a negative result.

## 2026-11-25, Step 3b build: LoRA with more room (not yet run)
- **Why:** in notebook 03, LoRA at 3e-4 was still climbing steeply at epoch 30, so its loss may be a time limit, not a ceiling. Before reporting LoRA as a negative result it gets a fair chance.
- **What:** `notebooks/03b_lora_longer.ipynb`: LoRA at 3e-4 and at 1e-3, 60 epochs each, type and escalation heads only (the same heads as the baseline, so only LoRA differs; notebook 03's LoRA also carried the language head). Same folds, input, seeds and LoRA size. The 60-epoch runs are also read at epoch 30. Compared with the baseline and notebook 03's 30-epoch LoRA run, read from the repo. About 30 to 35 minutes on a T4.
- **Checked here (no training):** the analysis cells ran on fake 60-epoch runs made by repeating notebook 03's saved LoRA runs; the baseline and LoRA rows reproduce notebook 03 exactly.
- **Bias, stated up front:** trying more LoRA settings and keeping the best, on the folds it is scored on, favours LoRA slightly.

## 2026-11-26, Step 4 result: comparison models on the pool
- **What:** ran `notebooks/04_baselines_haiku_sonnet_jev.ipynb` on a Kaggle CPU session (commit `a06357b`; run config in `results/step04/run_config.json`). 16 runs x 160 pool chats (Haiku and Sonnet 3 repeats, Jev 2, two inputs each) plus 40 one-at-a-time speed calls per model. Every answer is in `results/step04/preds/`, every raw reply in `results/step04/cache/` (2,680 files; the notebook replays from them for free), tables and figure in `results/step04/`.
- **Run notes:** the first attempt stopped on Sonnet's full-conversation runs with HTTP 402 "in-flight budget exhausted": the API key had its own $8 cap with $3.83 left, and OpenRouter holds money back for calls in progress. Neeraj raised the cap; the rerun with 3 parallel calls reused every saved answer. 0 unusable answers, 0 correction calls, 0 errors in all 2,560 scored answers. Recorded cost of the scored runs $5.70 (Sonnet $5.31). Jev's reply matched the documented shape (an answer and probabilities per question; the yes/no answer has no confidence field); its two repeats agree on 98% of request types.
- **Came out (160 pool chats; mean ± sd over runs, "combined" = average of runs; `comparison_pool.csv`):**

  | Method | Input | Type accuracy | Escalation recall | Escalation precision | Combined type acc [95% CI] | $ per chat |
  |---|---|---|---|---|---|---|
  | tuned XLM-R (notebook 02, epoch 30) | first message | 0.719 ± 0.050 | 0.720 ± 0.022 | 0.863 ± 0.046 | 0.756 [0.68, 0.83] | ~0 |
  | Haiku 5.5 | first message | 0.875 ± 0.006 | 0.961 ± 0.008 | 0.901 ± 0.015 | 0.875 [0.83, 0.92] | 0.000328 |
  | Sonnet 5.5 | first message | 0.917 ± 0.004 | 0.971 ± 0.000 | 0.971 ± 0.000 | 0.919 [0.88, 0.96] | 0.005375 |
  | Jev 1.14 | first message | 0.853 ± 0.004 | 0.986 ± 0.000 | 0.850 ± 0.000 | 0.856 [0.81, 0.90] | 0.000074 |
  | tuned XLM-R | full conversation | 0.750 ± 0.006 | 0.783 ± 0.043 | 0.875 ± 0.014 | 0.775 [0.70, 0.85] | ~0 |
  | Haiku 5.5 | full conversation | 0.800 ± 0.013 | 0.986 ± 0.000 | 0.861 ± 0.011 | 0.800 [0.74, 0.86] | 0.000372 |
  | Sonnet 5.5 | full conversation | 0.838 ± 0.006 | 0.981 ± 0.008 | 0.923 ± 0.007 | 0.838 [0.77, 0.89] | 0.005689 |
  | Jev 1.14 | full conversation | 0.800 ± 0.000 | 0.928 ± 0.000 | 0.901 ± 0.000 | 0.806 [0.75, 0.86] | 0.000078 |

  Language accuracy 1.000 for all three API models on both inputs.
- **Paired tests against the tuned model** (combined answers; `paired_tests_pool.csv`): first message: Haiku right on 29 chats the tuned model missed vs 10 the other way (p = 0.003), Sonnet 33 vs 7 (p < 0.001), Jev 26 vs 10 (p = 0.011). Full conversation: Haiku 25 vs 21 (p = 0.66), Sonnet 27 vs 17 (p = 0.17), Jev 20 vs 15 (p = 0.50).
- **Speed, one call at a time from Kaggle** (`latency.csv`, 39 calls after a warm-up): Jev median 200 ms (p90 222), Sonnet 1,004 ms (p90 2,035), Haiku 2,340 ms (p90 2,822).
- **Where each wins** (`type_recall_by_method.csv`, `type_accuracy_by_language.csv`, first message): French type accuracy tuned 0.64 vs Haiku 0.84, Jev 0.77, Sonnet 0.91 (English 0.82 vs 0.89, 0.90, 0.92). needs_human: tuned 0.56, Haiku 0.56, Sonnet 0.88, Jev 1.00. The tuned model beats all three API models only on roadside_assistance (0.88 vs 0.75 to 0.81); it ties or beats Jev alone on a few more types.
- **Reading:**
  - On the production input (first message) every API model beats the tuned model clearly, by 10 to 16 points on request type (combined answers), and much more on escalation: the tuned model misses about 1 in 4 chats that need a person (recall 0.72), the API models about 1 to 4 in 100. This is the negative result the brief asks to report plainly.
  - All three API models do worse with the full conversation (6 to 8 points), the tuned model slightly better, so on that input no difference is significant. A likely reason: the label follows the opening request and the later turns add other topics (warranty_claim recall drops from 0.94 to 0.69 for Haiku). Not tested.
  - The tuned model wins only on cost and speed. Jev comes close to Haiku on type (0.856 vs 0.875), has the best escalation recall, is about 4 times cheaper and 12 times faster than Haiku, and its questions were written once, not tuned.
  - Haiku's and Sonnet's pool scores are slightly optimistic: the team tuned their prompt on the 30 validation chats, which are in the pool. The 40 test chats are the clean comparison.
- **Next:** decide with Neeraj. The saved answers allow, with no new API cost: the tuned model's escalation threshold, a cascade (tuned model first, Jev or Haiku for unsure chats) and how often Jev, Haiku and Sonnet agree on the escalation reason.

## 2026-11-26, Step 3b result: LoRA with more room
- **What:** ran `notebooks/03b_lora_longer.ipynb` on a Kaggle T4 (commit `a06357b`): LoRA at 3e-4 and 1e-3, 60 epochs, type and escalation heads, 2 x 3 seeds x 5 folds = 30 runs, about 49 s per run. Raw scores in `results/cv_step03b/`; tables, figure and the executed notebook in `results/step03b/`. (The smoke-test time estimate, 272 minutes, was inflated by the first model download; the real run took about 25 minutes.)
- **Came out (160 out-of-fold chats, mean ± sd over 3 seeds; `cv_summary_step03b.csv`, `comparisons_step03b.csv`):**

  | Model | Epoch | Type macro-F1 | Escalation F2 | Escalation recall (missed of 69) | Combined type acc [95% CI] | vs baseline (only model right / only baseline right, p) |
  |---|---|---|---|---|---|---|
  | baseline (full fine-tuning) | 27 | 0.722 ± 0.043 | 0.739 ± 0.013 | 0.715 (19.7) | 0.788 [0.72, 0.86] | |
  | LoRA 3e-4, 30 epochs (notebook 03, with language head) | 30 | 0.635 ± 0.042 | 0.730 ± 0.017 | 0.720 (19.3) | 0.688 [0.61, 0.76] | 8 / 24, p = 0.007 |
  | LoRA 3e-4, 60 epochs | 60 | 0.723 ± 0.029 | 0.796 ± 0.032 | 0.787 (14.7) | 0.762 [0.70, 0.83] | 11 / 15, p = 0.56 |
  | LoRA 1e-3, 60 epochs | 58 | 0.702 ± 0.074 | 0.749 ± 0.102 | 0.729 (18.7) | 0.775 [0.70, 0.85] | 11 / 13, p = 0.84 |

- **Learning curves** (`learning_curves_03b.png`): LoRA at 3e-4 needs about 40 epochs to reach the plateau full fine-tuning reaches at 18, then sits at the same level (about 0.70 to 0.73). LoRA at 1e-3 learns as fast as full fine-tuning but plateaus a little lower and varies much more between seeds.
- **Reading:**
  - Given 60 epochs, LoRA at 3e-4 matches full fine-tuning on request type (no measurable difference), is steadier between seeds (sd 0.029 vs 0.043), catches more escalations (F2 0.796 vs 0.739, a gap larger than either spread; about 5 fewer missed chats out of 69), and trains in the same time (49 s for 60 epochs vs about 53 s for 30). Notebook 03's LoRA loss was a time limit, not a ceiling.
  - Read at epoch 30, the two-head LoRA run (macro-F1 0.688) is above notebook 03's three-head LoRA run (0.635) at the same learning rate; one more hint, untested, that the language head costs request-type accuracy.
  - Neither changes the comparison with the API models (combined type accuracy 0.76 to 0.79 here vs 0.86 to 0.92 for Jev, Haiku and Sonnet on the first message).
- **By the selection rules written before the results (EVAL_PROTOCOL section 7):** type macro-F1 is a tie (0.723 vs 0.722); escalation F2 favours LoRA 3e-4 at 60 epochs. The escalation rule is defined "at the threshold chosen above", and no threshold has been chosen yet, so the pick between full fine-tuning and LoRA is made after the threshold analysis.
- **Bias:** LoRA got three settings tried on these folds, full fine-tuning one; a slight advantage to LoRA in this comparison.

## 2026-11-26, team repo review: what changes for the router
- **What:** read the team repo (`Salikawtar/northstar-agent`, tip `0cc6208`) and Libo's evaluation hand-off. The team's agent uses the **Haiku** router. Kawtar's fine-tuned router (choices on the 30 validation chats, three heads, full conversation) scored 67.5% on test type and **40% task success in the whole agent against 70% with Haiku** (12 chats lost, none won, p = 0.0005). The main cause: 8 of its 17 handoffs reached the wrong team, 7 of them attacks, because `predict.py` guesses the reason from the request type, and attacks are spread over all 10 types (4 per type in the dataset).
- **Found:** the team's grader decides the acceptable team from two dataset columns (`request_type`, `adversarial_type`; `evaluation/rules.py`). So the team a handoff reaches can be scored with real labels, and "is this an attack?" is a real label the model can learn (31 in the pool, 5 kinds).
- **Also from the team repo:** a data-size curve (+28 points per doubling), a break-even study ($71 a month server; beats Haiku above 197,000 chats a month), a LoRA check on validation (she kept full fine-tuning; she noted 3e-4 was under-trained), a fresh held-out set of 32 chats from another model family (`data/fresh/fresh_chats.csv`), and a harness that reruns the agent from a router's recorded answers. Libo's hand-off gives Neeraj one high-priority action: escalation-reason prediction, judged by the right-team rate.
- **Decisions (Neeraj, 2026-11-26):** language by the word rule; the reason is judged by the right-team rate; three router options compared on the pool (tuned alone with an attack answer; tuned + Jev or Haiku reason step; a language model alone). Protocol updated before any of our routers was scored this way.

## 2026-11-26, Step 5 and 3c build: router options and the attack answer (not yet run)
- **Code:** `routing.py` (the team's handoff and grader rules, copied from commit `0cc6208`, and the word rule), `router_options.py` (the options built from saved answers), an `attack` head in `model.py`, `train_cv.py`, `protocol.py` (`attack_label` = non-empty `adversarial_type`) and `cv_analysis.py`.
- **Notebook 03c (GPU, about an hour):** full fine-tuning (2e-5, 30 epochs) and LoRA (3e-4, 60 epochs), each with type, escalation and attack answers, on the first message and the full conversation.
- **Notebook 05 (CPU, free):** escalation cut-off by F2 on the pool for each tuned model, the protocol's full fine-tuning vs LoRA pick, the word rule, every option scored on type, handoffs, right team, attacks, extra handoffs, share of chats calling a language model and cost; paired tests against Haiku alone; reason agreement between the language models. It adds option 1 by itself once notebook 03c's runs are in the repo.
- **Checked here (no training, no API calls):** the word rule gets the language right on all 160 pool chats for both inputs; the scoring reproduces the team's finding on our pool (her type rule sends 6 of 31 attacks to the right team, Haiku alone 30 of 31); both notebooks' analysis cells ran end to end, notebook 03c's on fake runs.

## 2026-11-26, Step 5 result: router options scored by the team that gets the handoff
- **What:** ran `notebooks/05_router_options.ipynb` on a Kaggle CPU session (commit `74fcb57`), no API calls. Notebook 03c had not run yet, so option 1 (attack answer) is not in it. Results in `results/step05/` (`router_options.csv`, `tuned_candidates.csv`, `paired_vs_haiku.csv`, `reason_agreement.csv`, `language_word_rule.csv`, `right_team_vs_cost.png`, executed notebook).
- **Word rule:** language right on all 160 pool chats, both inputs.
- **Tuned models (escalation cut-off chosen by F2 on the pool):** full fine-tuning, first message: cut-off 0.05, 7 of 69 handoffs missed, 26 false alarms; LoRA 60 epochs: cut-off 0.10, 10 missed, 16 false alarms. The protocol's rule picks LoRA (request type a tie; escalation F2 at the cut-off 0.847 vs 0.842, a negligible gap).
- **Options, first message (69 chats need a person, 31 of them attacks; "handled right" = person or not, and the right team, over all 160 chats):**

  | Option | Right team | Attacks right | Missed | Extra handoffs | Handled right | Language model used on | $ per 1,000 chats | vs Haiku alone (only option right / only Haiku right, p) |
  |---|---|---|---|---|---|---|---|---|
  | Haiku alone (the team's agent) | 65 of 69 | 30 of 31 | 3 | 9 | 0.919 | 100% | 0.33 | |
  | Sonnet alone | 66 | 31 | 2 | 3 | 0.963 | 100% | 5.38 | 8 / 1, p = 0.039 |
  | Jev alone | 60 | 24 | 1 | 22 | 0.806 | 100% | 0.07 | 7 / 25, p = 0.002 |
  | Tuned (full FT), her type rule | 38 | 6 | 4 | 36 | 0.581 | 0% | 0 | 4 / 58, p < 0.001 |
  | Tuned (full FT) + Haiku reason | 59 | 26 | 4 | 36 | 0.713 | 55% | 0.19 | 4 / 37, p < 0.001 |
  | Tuned (full FT) + Haiku reason + cascade | 61 | 28 | 4 | 27 | 0.781 | 63% | 0.21 | 4 / 26, p < 0.001 |
  | Tuned (LoRA) + Haiku reason + cascade | 59 | 22 | 9 | 17 | 0.831 | 50% | 0.17 | 5 / 19, p = 0.007 |
  | Tuned (full FT) + Jev reason + cascade | 55 | 23 | 4 | 29 | 0.731 | 63% | 0.05 | 5 / 35, p < 0.001 |

  Full conversation: the same picture (Haiku alone 66 of 69, handled right 0.912; best tuned option, full FT + Haiku reason + cascade, 61 of 69, 0.794, p < 0.001); Jev's reason collapses on this input (it calls 19% of attacks "adversarial", against 68% on the first message).
- **Reason agreement on the chats needing a person** (`reason_agreement.csv`): Haiku and Sonnet agree on 88%; Jev agrees with them on 72 to 74% (first message) and 46 to 54% (full conversation). Attacks called "adversarial": Sonnet 100%, Haiku 87%, Jev 68% (first message).
- **Reading:**
  - A reason step fixes most of the team problem: with Haiku's reason, 59 to 61 of 69 handoffs reach the right team instead of 38 with the type rule, and 26 to 28 of 31 attacks instead of 6.
  - It does not make the tuned router as good as Haiku alone. What remains is the tuned model's yes/no on "needs a person": with the F2 cut-off it sends 27 to 36 chats to a person who did not need one (the team's grader counts each as a failure), and with LoRA it misses 9. Every tuned option is clearly worse than Haiku alone on "handled right" (p from 0.007 to below 0.001).
  - It also keeps most of the cost: the best hybrid calls Haiku on 50 to 63% of chats and saves at most half of a router bill that is $0.33 per 1,000 chats.
  - Jev is not a drop-in replacement: cheap and fast, but its reason is weak (worst on the full conversation) and it sends 22 chats to a person who did not need one.
  - Sonnet alone is the best router on the pool (better than Haiku on the first message, p = 0.039; not on the full conversation, p = 0.23) at 16 times the cost; the team's end-to-end test found no gain from it.
- **Not settled here:** option 1 (attack answer) waits for notebook 03c. The escalation cut-off was chosen by F2 (missing a handoff counts double), while the team's grader counts a missed and an extra handoff the same; a cut-off chosen for "handled right" would trade misses for fewer extra handoffs (a sensitivity check, not a new selection).

## 2026-11-26, comparison scorecard
- **What:** `src/northstar/finetune/comparison_report.py` builds one comparison of every router setup on the 160 pool chats from saved results only (no training, no API calls): `results/comparison/routers_pool.csv` (21 setups: Haiku, Sonnet, Jev alone; fine-tuned full and LoRA alone and with a Haiku or Jev reason step, with and without the cascade; both inputs) and `results/comparison/training_variants.csv` (8 training setups). The `page_*.csv` files are the same numbers, rounded for display, plus the team's own test-set results copied from the team repo (commit `0cc6208`).
- **Published:** the scorecard page "Northstar Router Scorecard" (private claude.ai artifact) shows these four tables with definitions and caveats.
- **Numbers:** identical to notebook 05 where they overlap (for example, handled right on the first message: Haiku 91.9%, Sonnet 96.2%, Jev 80.6%, best fine-tuned setup 83.1%).

## 2026-11-26, Step 4b build: Jev with the same information as Haiku and Sonnet (not yet run)
- **Found (Neeraj asked for the check):** in notebook 04, Jev was not told what Haiku and Sonnet were told. It got the request types, the tie-breaks and the escalation rules (on its yes/no question only), but none of the prompt's 6 worked examples, and its reason question had one-line definitions written by us (for example "the message deliberately tries to trick the assistant" instead of the prompt's five kinds of attack and its list of what is not an attack). Instruction length per question was 158 to 2,174 characters.
- **Version 2** (`jev_questions_v2` in `baselines.py`, model key `jev2`, same model `typesafe/jev-1.14`): every question gets the team prompt's rules (first paragraph, Request types, Escalation, Language), the 6 worked examples with that question's answer, and reason definitions copied from the prompt; about 5,000 characters per question. Left out: the lines about returning JSON and a confidence number. Still different by design: Jev answers each question on its own.
- **Cost note:** Jev is priced per word read and repeats the instructions for each of its four questions, so version 2 reads about twice the text Haiku reads per chat. The run measures the real cost.
- **Notebook 04b** (CPU, key needed, expected well under $1, hard stop $3) runs version 2 on the pool with both inputs and 2 repeats, plus 40 one-at-a-time speed calls, and compares it with version 1, Haiku and Sonnet. Notebook 05 and `comparison_report.py` now include Jev version 2 automatically when `results/step04b/preds` exists. Checked here with a fake network and fake answers: the calls carry the version-2 questions, version 1 is unchanged, and the notebook 04b, notebook 05 and scorecard code all run with version 2 present.
- **Iteration count (protocol section 9):** Jev's questions are now on version 2 on the pool; Haiku's and Sonnet's prompt had three team versions.

## 2026-11-26, Step 3c result: the attack answer
- **What:** ran `notebooks/03c_attack_head.ipynb` on a Kaggle T4 (commit `74fcb57`): full fine-tuning (2e-5, 30 epochs) and LoRA (3e-4, 60 epochs) with type, escalation and attack answers, on the first message and the full conversation; 4 x 3 seeds x 5 folds = 60 runs, all complete. Raw scores in `results/cv_step03c/`; tables and the executed notebook in `results/step03c/`.
- **Came out (160 pool chats, each setup at its own best epoch; attack answer at the plain 50% cut-off; `attack_head_summary.csv`):**

  | Setup | Input | Type macro-F1 (without attack answer) | Type vs without: only new right / only old right (p) | Attacks caught, combined (of 31) | False attack alarms (of 129) | Attack recall / precision, mean of seeds |
  |---|---|---|---|---|---|---|
  | Full fine-tuning | first message | 0.632 ± 0.069 (0.722) | 4 / 15 (p = 0.02) | 14 | 0 | 0.45 / 0.95 |
  | Full fine-tuning | full conversation | 0.752 ± 0.024 (0.747) | 9 / 10 (p = 1.00) | 20 | 0 | 0.68 / 0.95 |
  | LoRA 60 epochs | first message | 0.722 ± 0.047 (0.723) | 10 / 6 (p = 0.45) | 14 | 1 | 0.52 / 0.93 |
  | LoRA 60 epochs | full conversation | 0.707 ± 0.014 (none) | | 16 | 1 | 0.54 / 0.90 |

- **By kind** (best setup by attack F2, `attacks_by_kind.csv`): manufacturer impersonation 5 of 5, policy pressure 6 of 7, personal-data extraction 4 of 7, prompt injection 4 of 6, warranty fraud 1 of 6.
- **Reading:** the model learns part of "is this an attack" from 31 examples: when it says attack it is almost always right, but at the plain cut-off it finds only about half of them (two thirds with the full conversation, which is where the later turns often carry the attack). Warranty fraud is nearly invisible to it. The extra answer costs nothing on request type except for full fine-tuning on the first message, where it lowered type accuracy (p = 0.02). Notebook 05 chooses the attack cut-off by F2 on the pool and scores option 1 by the team it sends handoffs to; it needs these runs on GitHub first.

## 2026-11-26, notebook 05 update: desk check, unsure line, safety view (not yet run on Kaggle)
- **Found:** "handled right" counted a chat the AI kept as right even when a wrong request type sent it to the wrong specialist desk; the team's AI judge would usually fail that chat. Now `routing.route_all` also checks the desk (`DESK_FOR`, copied from the team's `agent/specialist.py`). Previewed on the pool: every router loses 1 to 6 points and the order does not change (first message: Haiku 91.9% -> 90.0%, Sonnet 96.3% -> 95.0%, LoRA + attack answer 78.7% -> 75.6%).
- **Extra handoffs, where they come from** (LoRA + attack answer, first message, needs-a-person cut-off 5%): 11 from contested-charge rules after the very sensitive needs-a-person answer, 10 from the team's unsure rule (below 55% confidence goes to a person; the line was set for Haiku), 4 from "customer wants a person", 2 from false attack alarms, 1 from roadside.
- **Unsure line rule** (`router_options.choose_floor`, protocol section 7): the line with the best strict handled-right that never misses more handoffs than the team's 55%. Previewed: LoRA + attack answer, first message, chooses 40%: extra handoffs 24 -> 15, missed unchanged at 6, kept with the wrong desk 5 -> 8, strict handled-right 75.6% -> 79.4% (Haiku 90.0%, p = 0.009). A less sensitive needs-a-person answer would cut more extra handoffs but miss more people, so it is not used (safety first).
- **Attack cut-off check** (LoRA + attack answer, first message): lowering the cut-off only adds catches: 50% catches 14 of 31 with 1 false alarm, 5% catches 24 with 6, 1% catches 25 with 16; 6 attacks score under 1% and no sensible cut-off reaches them (mostly warranty fraud).
- **Notebook 05** now shows safety columns (missed, right team, attacks) and efficiency columns (extra handoffs, kept with the wrong desk), both handled-right versions, and option 1 with its own unsure line; it saves the line choice in `unsure_line_choice.csv`. `comparison_report.py` builds the scorecard's tables itself, including the attack-head options. Checked offline on the real saved runs; to be run on Kaggle after notebook 04b.

## 2026-11-26, Step 4b result: Jev with the same information as Haiku and Sonnet
- **What:** ran `notebooks/04b_jev_equal_information.ipynb` on a Kaggle CPU session (commit `214fae1`): Jev version 2 on the 160 pool chats, both inputs, 2 repeats, plus 40 one-at-a-time speed calls. 640 answers, 0 unusable, 0 errors; $0.16 for the scored runs. Answers in `results/step04b/preds/`, replies in `results/step04b/cache/`, tables and the executed notebook in `results/step04b/`.
- **Came out (first message; `jev_v2_comparison.csv`, rule-checks-only handled-right as computed at that commit):** type right 91.2% (version 1 85.6%, Haiku 87.5%, Sonnet 91.9%); needs a person caught 65 of 69 with 3 false alarms (Haiku 66 and 8); attacks called adversarial 31 of 31 (version 1 21, Haiku 27, Sonnet 31); handoffs to the right team 63 of 69 (Haiku 65); attacks to the right team 31 of 31 (Haiku 30); extra handoffs 10 (Haiku 9). Against Haiku: 7 chats only Jev right, 10 only Haiku right, p = 0.63 (full conversation p = 0.61). Against version 1: 22 vs 7, p = 0.008 (full conversation 37 vs 8, p < 0.001).
- **Cost and speed:** about 5,900 input tokens per chat (the rules are repeated for each of the four questions), $0.25 per 1,000 chats (version 1 $0.07, Haiku $0.33); median 0.46 s per call (version 1 0.20 s, Haiku 2.34 s).
- **With the strict measure (desk checked; `comparison_report.py`, first message):** Sonnet 95.0%, Haiku 90.0%, Jev version 2 90.0% (p = 1.00 against Haiku), Jev version 1 80.0%, best fine-tuned option (LoRA + attack answer + own unsure line 40%) 79.4%; the hybrids with a Jev version 2 reason step reach 74 to 78%, no better than with a Haiku reason step. Full conversation: Sonnet 88.8%, Haiku 86.2%, Jev version 2 85.6%.
- **Reading:**
  - Jev's weak first result came from what it was told, not from the model: given the same rules and examples as Haiku, it matches Haiku on the whole handoff decision, beats it on request type (91% vs 88%) and on attacks (31 of 31), and is about 25% cheaper and 5 times faster per call.
  - Its cost rose about 3.4 times from version 1 because Jev reads the full rules once per question; dropping the language question (the word rule already does it) or shortening shared text would cut that.
  - A reason step from Jev version 2 does not rescue the fine-tuned router: what remains is the fine-tuned model's own misses and extra handoffs.
  - Caveats: pool chats (the team tuned the prompt on 30 of them, which helps every model that reads it); this is Jev's second question version on the pool; Jev is in early access behind an "alpha" address. The test chats are the clean check.

## 2026-11-26, Step 5 result, second run: every option, strict measure
- **What:** reran the updated `notebooks/05_router_options.ipynb` on a Kaggle CPU session (commit `65eee80`) with the attack-head runs and Jev version 2 present. Files in `results/step05/` replace the first run's (the first run's executed notebook stays as `05-router-options.ipynb`; this one is `05-router-options-v2.ipynb`; the first run's tables are in git history). The numbers match `comparison_report.py` exactly.
- **Came out (first message; 69 chats need a person, 31 attacks, 91 do not; strict handled-right; p against Haiku alone):**

  | Router | Missed | Right team | Attacks right | Extra handoffs | Kept, wrong desk | Handled right | p | $ per 1,000 | Seconds |
  |---|---|---|---|---|---|---|---|---|---|
  | Sonnet alone | 2 | 66 | 31 | 3 | 2 | 95.0% | 0.039 | 5.38 | 1.00 |
  | Haiku alone (team) | 3 | 65 | 30 | 9 | 3 | 90.0% | | 0.33 | 2.34 |
  | Jev, same information | 4 | 63 | 31 | 10 | 0 | 90.0% | 1.00 | 0.25 | 0.46 |
  | Jev, first version | 1 | 60 | 24 | 22 | 1 | 80.0% | 0.007 | 0.07 | 0.20 |
  | LoRA + attack answer, own unsure line 40% | 6 | 59 | 25 | 15 | 8 | 79.4% | 0.010 | 0 | 0.25 (team CPU figure) |
  | LoRA + Jev v2 reason + Jev v2 when unsure | 9 | 58 | 23 | 16 | 9 | 77.5% | < 0.001 | 0.12 | 0.25 + 0.46 on 50% |
  | LoRA + attack answer, team line 55% | 6 | 59 | 25 | 24 | 5 | 75.6% | < 0.001 | 0 | 0.25 |
  | Full fine-tuning + attack answer | 2 | 62 | 28 | 45 | 5 | 64.4% | < 0.001 | 0 | 0.25 |
  | Full fine-tuning, reason from type (her rule) | 4 | 38 | 6 | 36 | 6 | 54.4% | < 0.001 | 0 | 0.25 |

  Full conversation: Sonnet 88.7%, Haiku 86.3%, Jev version 2 85.6% (p = 1.00), best fine-tuned 77.5% (full fine-tuning + Jev v2 reason + cascade), best without a language model 72.5% (full fine-tuning + attack answer, own unsure line 45%).
- **Unsure line chosen by the rule:** LoRA + attack, first message 40%; full fine-tuning + attack, full conversation 45%; the other two kept 55% (a lower line would have missed more handoffs).
- **Reason agreement on chats needing a person (first message):** Jev v2 agrees with Sonnet on 97% and with Haiku on 86%; Haiku and Sonnet 88%. Attacks called adversarial: Jev v2 and Sonnet 100%, Haiku 87%, Jev v1 68%.
- **Reading:** no fine-tuned option reaches Haiku or Jev version 2 on the pool; the best one without any language model (LoRA + attack answer + own unsure line) is about 11 points behind, missing 3 more chats that need a person and sending 6 more to a person who did not need one, at no cost per chat. Hybrids that call a language model for the reason are no better than that and keep half the cost. Jev version 2 is the cheapest and fastest router that matches Haiku.
- **Open (for Neeraj):** the safety-first rule written in section 7 ranks full fine-tuning + attack answer first (2 missed, 28 attacks right) even though it sends 45 of 91 ordinary chats to a person; LoRA + attack + own line is far better overall but misses 6. Which fine-tuned setup goes to the test chats is decided before they are opened.

## 2026-11-26, Step 6 build: the final run (not yet run; test and fresh chats still closed)
- **Decision (Neeraj):** score both fine-tuned candidates. "Safest" (full fine-tuning + attack answer) is what the safety-first rule ranks first; "balanced" (LoRA + attack answer + own unsure line 40%) is far better overall. Declaring both now avoids changing the rule after seeing the test chats.
- **Frozen settings:** `config/final_settings.json`, taken from the pool results (notebook 05 second run, `results/cv_step03c`): inputs, epochs (27 and 60), cut-offs (escalation 0.05 and 0.10, attack 0.05), unsure lines (0.55 and 0.40), 5 seeds (101 to 105) averaged, word rule for language, language models and repeats (Haiku 3, Sonnet 3, Jev v2 2, Jev v1 2, both inputs), budget $6, and the pool estimates to compare against.
- **Fresh set added:** `data/fresh/fresh_chats.csv` copied from the team repo (commit `0cc6208`) with its review record, SHA-256 checked, 31 chats after the one rejected in review; locked like the test chats (`protocol.fresh_set`).
- **Code:** `final_run.py` (train on all 160 pool chats and score the held-out chats after the last epoch only, with zeros in place of their answers; combined and per-seed answers; CPU speed with 2 cores; the same scoring for every router; recordings in the format of the team harness's `RecordedRouter`, with the confidence rescaled so the team's 0.55 line acts as the router's own line). `train_cv.run_one` gained `score_every_epoch` and `return_model`. `notebooks/06_final_run.ipynb` runs it all, with a smoke test on practice chats first.
- **Checked here (no training, no held-out chat opened):** both locks refuse without `final=True` and the switch; the dataset still loads; the scoring, spread, recording and saving cells ran end to end with practice chats standing in for the held-out sets and fake model scores; the confidence rescaling keeps the order and maps 0.40 onto 0.55.

## 2026-11-26, Step 7 build and hand-over router (while the final run runs; not yet run)
- **Notebook 07** (`07_full_agent_test.ipynb`, Kaggle CPU + key): the team's own end-to-end test, unchanged: clones the team repo at `0cc6208` (the commit behind Libo's results), registers our routers through the harness's existing `RecordedRouter` (the way it ran Kawtar's model) and changes nothing else. Setups: `full_agent` (Haiku, replayed from the team's recorded calls, so it should reproduce Libo's 70% and 67.7% at no cost: a built-in check), fine-tuned balanced, fine-tuned safest, Jev with the same information (full conversation, as Haiku reads it in the agent), and Kawtar's recorded router on the test chats for continuity. Same judge and rules; paired tests against the Haiku agent. Not checked here: it needs the team's code, the key and the final run's recordings.
- **`final_run.llm_recording`:** builds the same recording for a language-model router from its saved answers (for Jev in the agent).
- **Hand-over router** (`handover_router.py`, `TunedRouter`): loads XLM-RoBERTa base once plus the trained LoRA parts of each seed (a few MB each, swapped in per pass), applies the frozen cut-offs, the attack-to-reason rule, the word rule and the confidence map; `route(turns)` returns the team's `RouteResult` inside the team repo. Its decision rules are checked here; loading the trained weights is checked on Kaggle once the final run's weights exist.

## 2026-11-26, reviewer readiness: no secrets, keyless replay, tests
- **Secrets:** scanned every tracked and untracked file, the executed notebooks' outputs and the whole git history for API keys, tokens, `.env` files and personal email addresses: none. The OpenRouter key only ever lives in Kaggle's secret store.
- **Keyless replay:** `baselines.Client(None, cache)` replays saved answers and raises `ReplayMiss` at the first call it has not seen. Notebooks 04, 04b and 06 copy the answers saved in the repo into their cache first and run without a key; notebook 07 does the same with the team client in replay mode. (The logic of runs already made is unchanged; only the start of these notebooks changed.)
- **Tests:** `tests/` (29 tests, about 25 seconds, no GPU, network or key): dataset check and locks, input variants, word rule, the team's handoff and grader rules, the desk check, answer parsing, the client with a fake network and keyless replay, refused unusable runs, the final run's scoring and recordings, and recomputed headline numbers (notebook 02 baseline 0.719 and 0.756; Haiku alone 65, 30, 3, 9 and 90.0%; Jev v2 31 attacks and 90.0%; her rule 38, 6, 54.4%; balanced setup epoch 60, line 0.40, 6, 59, 25, 15, 79.4%; frozen settings equal to the pool results).
- **`requirements.txt`** and a reviewer section at the top of `README.md`. The router class (`handover_router.py`) is for our own integration of the model into the team's flow later; nothing is handed over.

## 2026-11-26, Step 6 result: the final run (test and fresh chats, opened once)
- **What:** ran `notebooks/06_final_run.ipynb` on a Kaggle T4 (commit `21a74de`). The test and fresh sets were opened once (`results/step06/test_access.log`, 19:33:27). Both fine-tuned setups trained on all 160 pool chats with seeds 101 to 105 (about 55 s per run), scored only after the last epoch. 20 language-model runs on the 71 held-out chats, 0 unusable answers, $2.61. Everything is in `results/step06/` (scores, per-seed scores, CPU speed, every answer and reply, the balanced setup's trained LoRA parts, recordings for the team harness, the executed notebook).
- **Speed of the fine-tuned router:** 0.15 s per chat for one model on 2 CPU cores (median; p90 0.17 s). Language-model speeds are the one-at-a-time medians measured on the pool (Haiku 2.34 s, Sonnet 1.00 s, Jev v2 0.46 s).
- **Test chats (40; 18 need a person, 9 attacks), first message; strict handled-right [95% range]; paired against Haiku (only router right / only Haiku right):**

  | Router | Type right | French | Missed | Right team (of 18) | Attacks right (of 9) | Extra handoffs | Handled right | vs Haiku | $ per 1,000 |
  |---|---|---|---|---|---|---|---|---|---|
  | Haiku (team) | 82.5% | 92.9% | 0 | 18 | 9 | 2 | 90.0% [79-98] | | 0.32 |
  | Sonnet | 82.5% | 85.7% | 0 | 17 | 9 | 0 | 90.0% [79-98] | 2 / 2, p = 1.00 | 5.37 |
  | Jev, same information | 90.0% | 100% | 0 | 17 | 9 | 4 | 87.5% [76-97] | 1 / 2, p = 1.00 | 0.25 |
  | Jev, first version | 77.5% | 85.7% | 0 | 16 | 7 | 3 | 87.5% [75-97] | 2 / 3, p = 1.00 | 0.07 |
  | **Fine-tuned, balanced** | 80.0% | 92.9% | 2 | 15 | 8 | 1 | **87.5% [77-96]** | **2 / 3, p = 1.00** | **0** |
  | Fine-tuned, safest | 82.5% | 85.7% | 2 | 15 | 8 | 5 | 77.5% [64-90] | 1 / 6, p = 0.125 | 0 |
  | Kawtar's fine-tuned router (her recorded answers, same scoring) | 67.5% | 71.4% | 1 | 9 | 1 | 5 | 62.5% [46-78] | | 0 |

  Full conversation (language models only): Haiku 87.5%, Sonnet 82.5%, Jev v2 82.5%, Jev v1 70.0%.
- **Fresh chats (31; another model family, labelled under the team's final policy; 24 need a person, 9 attacks), first message:** Jev v1 77.4%, Sonnet 74.2%, Jev v2 74.2%, Haiku 71.0% [47-89], **fine-tuned balanced 51.6% [36-67]** (2 / 8, p = 0.109), safest 45.2% (3 / 11, p = 0.057). Request type: language models 87 to 90%, fine-tuned 55 to 58%. Full conversation: Haiku 77.4%, Sonnet 74.2%, Jev v2 71.0%.
- **Seeds alone (balanced):** test handled-right 83.5% ± 5.2 (80.0 to 92.5), fresh 44.5% ± 4.2; the five-seed combination is above the single-seed mean on both.
- **Reading:**
  - On chats like the ones it learned from (the test set, same generator), the balanced fine-tuned router is close to Haiku: 87.5% vs 90.0%, two chats differ each way, at no cost per chat and about 15 times faster. Against Kawtar's version on the same chats: request type 67.5% -> 80.0%, handoffs to the right team 9 -> 15 of 18, attacks 1 -> 8 of 9, handled right 62.5% -> 87.5%.
  - On chats written by a different model (the fresh set), it does not hold up: request type falls to 55% while the language models stay near 90%. With 160 training chats from one generator, it learned that generator's way of writing. This is the main limit and the strongest case for a language-model router or for more varied training data.
  - The practice-chat estimate for the balanced setup (79.4%) sat between its test (87.5%) and fresh (51.6%) results.
  - Every router misses 6 to 9 of the fresh chats that need a person. Five misses are shared by all four routers checked, and all five are chats whose label the team's reviewers changed to "needs a person" under the final policy (caregivers writing for someone, angry customers in capitals; `data/fresh/FROZEN.json`): a policy change none of the routers was told about, not a router fault.
  - Jev with the same information: best request type on the test set (90%), level with Haiku on both sets, at about three quarters of Haiku's cost and a fifth of its time.
  - Safest vs balanced: as designed, safest misses fewer people on the fresh set (4 vs 9) but sends more chats to staff (5 vs 1 on test) and ends lower overall on both sets.
  - Small sets: 40 and 31 chats; no difference against Haiku is statistically clear on either set.
- **After the run:** Kawtar's recorded test answers were scored with the same code (the test set opened once more, for this analysis only, logged locally); nothing was tuned.

## 2026-11-26, Step 7 result: the whole agent with each router (team's own end-to-end test)
- **What:** ran `notebooks/07_full_agent_test.ipynb` on a Kaggle CPU session: the team repo at `0cc6208` with our routers registered through its `RecordedRouter`, our repo at `f992eb2`. $0.79 of new calls; 125 new recorded calls are saved in `results/step07/llm_cache_new/` (for free replay), with the judge's records, the per-chat table and the executed notebook.
- **The setup is faithful:** the Haiku agent replayed at $0 and reproduced Libo's numbers exactly (test 70.0%, fresh 67.7%), and Kawtar's recorded router reproduced her 40.0%.
- **Task success (all five rubric questions pass and no rule check fails); paired against the Haiku agent (only Haiku agent right / only this router right, exact p):**

  | Router in the agent | Test (40) | vs Haiku | Fresh (31) | vs Haiku | Missed / extra handoffs (test) | Wrong team (test failures) | Policy failures (test) | Median s | $ per 1,000 replies |
  |---|---|---|---|---|---|---|---|---|---|
  | Haiku (team) | 70.0% [55-82] | | 67.7% [50-81] | | 0 / 6 | 0 | 3 | 5.59 | 5.34 |
  | **Fine-tuned, balanced** | **57.5%** [42-72] | 5 / 0, p = 0.06 | 38.7% [24-56] | 10 / 1, p = 0.012 | 2 / 5 | 1 | 12 | 4.36 | 5.58 |
  | Jev, same information | 55.0% [40-69] | 6 / 0, p = 0.03 | 61.3% [44-76] | 3 / 1, p = 0.63 | 2 / 6 | 1 | 9 | 3.79 | 5.47 (+0.25 router) |
  | Fine-tuned, safest | 47.5% [33-63] | 9 / 0, p = 0.004 | 38.7% | 10 / 1, p = 0.012 | 1 / 7 | 1 | 15 | 4.11 | 5.57 |
  | Kawtar's fine-tuned router | 40.0% [26-55] | 12 / 0, p = 0.0005 | (not recorded) | | 1 / 8 | 8 | 16 | 0.28 | 4.51 |

  (The agent's cost counts the desks and the Haiku router's calls; the recorded routers add $0 there; Jev's own $0.25 per 1,000 is added by hand. Kawtar's 0.28 s is as recorded in the team's run.)
- **Why the balanced router does worse in the agent than at the routing step (87.5% vs Haiku's 90.0% there):**
  - It gives the same router answer as Haiku on 24 of the 40 test chats; 4 of the 5 chats it loses have a different answer, 1 the same answer.
  - **The reason picks the reply, not only the team.** On 6 test chats both routers send the chat to a person but with a different reason; on 5 of them Haiku says "safety" and ours says "customer request" (accident chats the model typed as needs_human) or "adversarial" (roadside chats where the attack answer overrode safety). The safety reason triggers the fixed safety reply (do not drive, call 911; policy P07); the others do not, so the judge fails the reply. The routing-step score accepted these handoffs because the grader accepts several teams for them; the full agent shows the cost.
  - **Secondary request types:** Haiku names other requests in a chat (20 of 40 test chats); our routers never do, so the desk can answer only the main request (one lost chat, v3_0001, had the same main answer as Haiku).
  - **One run per chat:** a desk reply written once and judged once; a few differences can come from that.
- **Against Kawtar's version on the same test chats:** 40.0% -> 57.5% task success, wrong team among failures 8 -> 1, policy failures 16 -> 12.
- **No saving in the agent:** the desks' calls dominate the cost ($5.58 vs $5.34 per 1,000 replies; the fine-tuned router sends fewer chats down the free fast path); it is about 1.2 s faster per reply (4.4 s vs 5.6 s median).
- **Fresh chats:** the fine-tuned routers fall to 38.7% (type accuracy 55% at the routing step); Jev with the same information stays close to Haiku (61.3% vs 67.7%, p = 0.63).
- **Reading for the report:** fine-tuning on 160 synthetic chats gives a router that is fast, free per chat and close to Haiku at the routing step on familiar chats, but in the whole agent it is clearly behind Haiku (57.5% vs 70.0%) and fails on chats from another source. Haiku stays the router. Two concrete reasons the gap is larger in the agent are fixable in principle: a safety signal that sets the safety reply (and is never overridden by the attack answer), and secondary request types. Jev with the same information is the closest cheaper alternative but did not match Haiku in the agent on the test chats.

## 2026-11-28, Step 8: the team repo on a clean machine, and a speed correction
- **What:** `notebooks/08_team_repo_full_check.ipynb` on Kaggle (CPU, no key): cloned the team repo with the study in it (branch `finetune-study` on my fork), installed `requirements.txt`, ran `run_all.py evaluate finetune economics` from the recordings and every test. Saved as `results/step08/` in the study.
- **Result:** 1,407 model calls, all replayed, $0. Every setup's task success equals the committed one (14 of 14). 283 of 284 tests passed; the one failure (the first router's LoRA test) came from Kaggle's `torchao` breaking `peft`, as in step 3, and passed once `torchao` was removed.
- **The live model:** the five trained LoRA seeds, run on CPU, made exactly the recorded decisions on the 40 test chats (type, person, reason; largest confidence gap 0.0011).
- **Correction:** step 6 timed one model (0.15 s a chat). The router that was scored averages five models: **0.74 s a chat** (median, 2 CPU threads, `results/step08/live_router_check.json`), about 3 times faster than Haiku, not 15. The agent's recording of this router now uses 0.74 s (`results/step08/router_finetuned-balanced_five_models_test_and_fresh.csv`); its median wait in the whole agent becomes 4.95 s on test (was 4.36) and 3.91 s on fresh (was 3.32). No decision, success rate or cost changes. The full fine-tuning variant also averages five models of the same size, so its time is about the same; it was not re-timed.
