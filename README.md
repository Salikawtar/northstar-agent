# Northstar Motors: Dealership Customer-Support Agent

MMAI 894 Deep Learning, 2026 team project. A bilingual (EN/FR) agent for the
service department of "Northstar Motors", a fictional Ontario dealership group
selling the fictional Meridian brand. All data is synthetic.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # add your OpenRouter key (needed from Phase 2)
python run_all.py             # rebuilds everything built so far and runs the tests
```

## Repository layout (mirrors the system design and the team roles)

| Folder | What it holds | Owner |
|---|---|---|
| `data/conversations/` | 200 synthetic chats as CSV (train 130 / validation 30 / test 40, grouped by customer) | Weidi |
| `data/redteam/` | 75 attacks for guardrail tests (never trained on) + dealer records for their customers | Weidi + team |
| `data/source/` | Review workbook v1112: human review, QC log, team decisions (source of truth for the CSVs) | Weidi |
| `data/dms/` | Mock dealer system generated from the chats | Kawtar |
| `src/northstar/data.py` | One loader for every dataset (`load_conversations`, `load_redteam`) | Team |
| `src/northstar/contracts.py` | Shared data shapes every module uses | Team (read `docs/contracts.md`) |
| `src/northstar/dms/` | Dealer system generator + tool API (verification enforced in code) | Kawtar |
| `src/northstar/agent/` | Router, specialist agents, single-agent baseline, handoff | Kawtar |
| `src/northstar/guardrails/` | Operating policy, input/output checks, log masking, attack tests | Jessica |
| `src/northstar/finetune/` | Fine-tuned router + small/large prompted baselines | Neeraj |
| `src/northstar/evaluation/` | Grader, metrics, experiment runner, error analysis | Libo |
| `src/northstar/economics/` | Cost model, volumes, break-even | Abhi |
| `config/settings.yaml` | All settings (models, effort, paths, failure injection) | Team |
| `tests/` | Unit tests for every module | Everyone |

Each module folder also holds a reference implementation built by Kawtar.
Teammates' versions plug in through the same contracts, and the evaluation
compares them on the same test set.

## Status

| Phase | Status |
|---|---|
| 1. Contracts, repo, mock dealer system | Done (41 tests passing, incl. dataset checks) |
| 2. Agent (router, specialists, baseline, handoff, failures) | Next |
| 3. Guardrails and attack test set | To do |
| 4. Evaluation and error analysis | To do |
| 5. Fine-tune and 3-model comparison | To do |
| 6. Cost model | To do |
| 7. One-command reproduction, final README | In progress (`run_all.py`) |

## Rules
- Never commit `.env` or any key.
- Change `contracts.py` only after team agreement; bump `CONTRACT_VERSION`.
- Code comments explain **why**, not only what.
