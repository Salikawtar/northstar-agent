# Fine-tuning and model comparison tasks tracker

> **Internal working file.** Decide whether to keep or remove it before the repository is shared with the evaluators.

**Main idea:** every task for Member 3 (fine-tuning and model comparison, 8 marks), what it is, where it feeds into the project, and whether it is done. **Owner: Neeraj.** The fine-tuned model replaces the router behind the same "plug" (the `RouterOutput` contract), so nothing else in the agent changes.

Status values: **Done**, **Decided**, **Partly built**, **To do**.

| # | Task | What it is | Where it is used | Status |
|---|---|---|---|---|
| 1 | Narrow task | Classify the request type and decide whether a person must take over (the router's job) | Report page 4; runs on every chat, so speed and cost matter | Decided (project outline) |
| 2 | Base model and method | Pick a small base model and a training method, and say why | Report page 4 | Done: XLM-RoBERTa base, learning rate 3e-5, chosen on validation macro F1 (DistilBERT multilingual lower; mDeBERTa crashed under mixed precision, logged) |
| 3 | Training data | The 130 training chats as input and output pairs (chat in, `RouterOutput` JSON out); the 30 validation chats for tuning; never the 40 test chats | Training run | Done in code: same three-turn text as the prompted router; train 130, validation 30, test never read during choices (a test checks this) |
| 4 | Training run | Train and record model version, hyperparameters, epochs, settings and training cost | Report page 4 and appendix; training cost for Abhi | Done: 5 seeds on a Kaggle T4, 1.3 min per run, 16 GPU minutes in all (about $0.12); `results/training_log.json` |
| 5 | Plug into the agent | The fine-tuned model answers in the `RouterOutput` format, chosen in `config/settings.yaml` | End-to-end agent with the fine-tuned router | Done: `predict.py` returns a full `RouterOutput`; `python -m northstar.agent.router --model finetuned` |
| 6 | Small prompted baseline | Claude Haiku 5.5 with the router prompt | Comparison table | Done: test 82.5% type accuracy, 100% escalation recall, $0.36 per 1,000 chats (validation 83%) |
| 7 | Large prompted baseline | Claude Sonnet 5.5 with the same router prompt | Comparison table | Done: Haiku and Sonnet on the 40 test chats (recorded, replayed for free) |
| 8 | Same task for all three | Same input, same output format, same test chats | Fair comparison (brief requirement) | Done: same input text, same evaluation script, same row-level scoring (`compare.py` checks the chat ids match) |
| 9 | Metrics | Macro F1 and per-class accuracy for the request type, escalation recall, latency, cost | Comparison table; outline promise | Done: macro F1, per-class accuracy, escalation recall and precision, language, latency, cost, 95% intervals, paired test |
| 10 | Test-set comparison | The three routers on the 40 test chats, run once, with Libo | Report page 4 results table | Done: `results/comparison_table.csv` and `MODEL_CARD.md` |
| 11 | Where it wins and loses | For example short English chats versus French and multi-ask chats | Report page 4 interpretation | Done: `MODEL_CARD.md` (loses on adversarial and French chats, wins on speed, cost, escalation precision and lease-end returns; in the agent, the confidence floor catches 8 of 13 mistakes) |
| 12 | When fine-tuning pays off | Monthly volume where the training cost is paid back by cheaper calls (with Abhi) | Report pages 4 and 7 | Done: one CPU server ($71 a month) makes it cheaper than Haiku above about 197,000 chats a month and Sonnet above 12,800 (`breakeven.py`; server price in `config/settings.yaml`, shared with Abhi's model) |
| 13 | Honest negative result | With about 16 training chats per type the fine-tune may lose; if so, say why and estimate the data size where it would win | Report page 4 (brief: "report a negative result clearly") | Done: accuracy rises about 28 points per doubling with no plateau; about 190 chats would close the test gap if the trend held, a few hundred to be safe (`datasize.py`, `MODEL_CARD.md`) |
| 14 | Scripts and logs in the repo | Training script, settings, model reference, training logs; no keys | GitHub submission; reproducibility | Done: `src/northstar/finetune/` (scripts, Kaggle notebook, logs, results); `python run_all.py finetune` |
| 15 | Report page 4 and appendix | Task, base model, splits, training setup, three-model table; hyperparameters and full tables in the appendix | Final report | Partly built: page 4 draft written; LoRA sentence to add after its Kaggle run |

## Reminder before submission

- [ ] Decide whether to keep or remove this file before sharing the repository with the evaluators.
