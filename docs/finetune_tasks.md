# Fine-tuning and model comparison tasks tracker

> **Internal working file.** Decide whether to keep or remove it before the repository is shared with the evaluators.

**Main idea:** every task for Member 3 (fine-tuning and model comparison, 8 marks), what it is, where it feeds into the project, and whether it is done. **Owner: Neeraj.** The fine-tuned model replaces the router behind the same "plug" (the `RouterOutput` contract), so nothing else in the agent changes.

Status values: **Done**, **Decided**, **Partly built**, **To do**.

| # | Task | What it is | Where it is used | Status |
|---|---|---|---|---|
| 1 | Narrow task | Classify the request type and decide whether a person must take over (the router's job) | Report page 4; runs on every chat, so speed and cost matter | Decided (project outline) |
| 2 | Base model and method | Pick a small base model and a training method, and say why | Report page 4 | To do |
| 3 | Training data | The 130 training chats as input and output pairs (chat in, `RouterOutput` JSON out); the 30 validation chats for tuning; never the 40 test chats | Training run | To do (labels final: dataset v1114, 87 of 200 need a person) |
| 4 | Training run | Train and record model version, hyperparameters, epochs, settings and training cost | Report page 4 and appendix; training cost for Abhi | To do |
| 5 | Plug into the agent | The fine-tuned model answers in the `RouterOutput` format, chosen in `config/settings.yaml` | End-to-end agent with the fine-tuned router | To do (the plug is ready: contract and router evaluation script) |
| 6 | Small prompted baseline | Claude Haiku 5.5 with the router prompt | Comparison table | Done on validation: prompt v3, 83% type accuracy, 93% escalation recall, $0.0004 per chat |
| 7 | Large prompted baseline | Claude Sonnet 5.5 with the same router prompt | Comparison table | To do (one command: `python -m northstar.agent.router --model <sonnet>`, a few cents) |
| 8 | Same task for all three | Same input, same output format, same test chats | Fair comparison (brief requirement) | Decided: all three go through the same router evaluation |
| 9 | Metrics | Macro F1 and per-class accuracy for the request type, escalation recall, latency, cost | Comparison table; outline promise | Partly built: type accuracy, escalation recall and precision, latency, cost already measured; macro F1 and per-class to add |
| 10 | Test-set comparison | The three routers on the 40 test chats, run once, with Libo | Report page 4 results table | To do |
| 11 | Where it wins and loses | For example short English chats versus French and multi-ask chats | Report page 4 interpretation | To do |
| 12 | When fine-tuning pays off | Monthly volume where the training cost is paid back by cheaper calls (with Abhi) | Report pages 4 and 7 | To do |
| 13 | Honest negative result | With about 16 training chats per type the fine-tune may lose; if so, say why and estimate the data size where it would win | Report page 4 (brief: "report a negative result clearly") | To do |
| 14 | Scripts and logs in the repo | Training script, settings, model reference, training logs; no keys | GitHub submission; reproducibility | To do (`src/northstar/finetune/`) |
| 15 | Report page 4 and appendix | Task, base model, splits, training setup, three-model table; hyperparameters and full tables in the appendix | Final report | To do |

## Reminder before submission

- [ ] Decide whether to keep or remove this file before sharing the repository with the evaluators.
