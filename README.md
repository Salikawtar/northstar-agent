# Northstar Motors: Dealership Customer-Support Agent

MMAI 894 Deep Learning, 2026 team project. A bilingual (EN/FR) agent for the
service department of "Northstar Motors", a fictional Ontario dealership group
selling the fictional Meridian brand. All data is synthetic.

## Quick start

```bash
pip install -r requirements.txt
pip install -e .              # lets Python find the project code in src/ (once)
cp .env.example .env          # add your OpenRouter key (needed from Phase 2)
python run_all.py             # rebuilds everything built so far and runs the tests
```

## Try the router

```bash
python -m northstar.agent.router --split validation                        # Claude Haiku 5.5
python -m northstar.agent.router --split validation --model compare_small  # GPT-6 Luna
python -m northstar.agent.router --split validation --prompt router/v2.md --effort none  # try a prompt or effort
```
Needs `OPENROUTER_API_KEY` in `.env` the first time; answers are recorded in
`data/llm_cache/`, so later runs replay for free. Results go to `outputs/results/`.

Try a specialist (its share of the validation chats, router decision taken from the labels):

```bash
python -m northstar.agent.specialist --agent booking_status --split validation
python -m northstar.agent.specialist --agent warranty_recall --split validation
python -m northstar.agent.specialist --agent billing_lease --split validation
```

Run the whole agent (router, then the fast path or a specialist) on the validation chats:

```bash
python -m northstar.agent.pipeline --split validation
```

Compare with the single-agent baseline (one model, every tool, no router):

```bash
python -m northstar.agent.baseline --split validation
```

Run the hand-written test chats (each one passes or fails):

```bash
python -m northstar.agent.scenarios
```

Decisions and their reasons: `docs/decision_log.md`. Prompt changes: `docs/prompt_log.md`.

## Repository layout (mirrors the system design and the team roles)

| Folder | What it holds | Owner |
|---|---|---|
| `data/conversations/` | 200 synthetic chats as CSV (train 130 / validation 30 / test 40, grouped by customer) | Weidi |
| `data/redteam/` | 75 attacks for guardrail tests (never trained on) + dealer records for their customers | Weidi + team |
| `data/source/` | Review workbook v1114: human review, QC log, team decisions (source of truth for the CSVs) | Weidi |
| `data/dms/` | Mock dealer system generated from the chats | Kawtar |
| `src/northstar/agent/` | Router, specialist engine, tool box, handoff | Kawtar |
| `src/northstar/llm.py` | One door for every model call (OpenRouter): retries, spending limit, replay cache | Kawtar |
| `data/llm_cache/` | Recorded model answers, so results can be replayed with no key and no cost | Generated |
| `src/northstar/data.py` | One loader for every dataset (`load_conversations`, `load_redteam`) | Team |
| `src/northstar/contracts.py` | Shared data shapes every module uses | Team (read `docs/contracts.md`) |
| `src/northstar/dms/` | Dealer system generator + tool API (verification enforced in code) | Kawtar |
| `src/northstar/agent/` | Router, specialist agents, single-agent baseline, handoff | Kawtar |
| `src/northstar/guardrails/` | Operating policy, input/output checks, log masking, attack tests | Jessica |
| `src/northstar/finetune/` | Fine-tuned router + small/large prompted baselines | Neeraj |
| `src/northstar/evaluation/` | Grader, metrics, experiment runner, error analysis | Libo |
| `src/northstar/economics/` | Cost model, volumes, break-even | Abhi |
| `prompts/` | Every prompt, versioned (`router/v1.md`...). Changes logged in `docs/prompt_log.md` | Kawtar |
| `config/settings.yaml` | All settings (models, effort, paths, failure injection) | Team |
| `tests/` | Unit tests for every module | Everyone |

Each module folder also holds a reference implementation built by Kawtar.
Teammates' versions plug in through the same contracts, and the evaluation
compares them on the same test set.

## Status

| Phase | Status |
|---|---|
| 1. Contracts, repo, mock dealer system | Done |
| 2. Agent (router, specialists, baseline, handoff, failures) | In progress (model client, router) |
| 3. Guardrails and attack test set | To do |
| 4. Evaluation and error analysis | To do |
| 5. Fine-tune and 3-model comparison | To do |
| 6. Cost model | To do |
| 7. One-command reproduction, final README | In progress (`run_all.py`) |

## Rules
- Never commit `.env` or any key.
- Change `contracts.py` only after team agreement; bump `CONTRACT_VERSION`.
- Code comments explain **why**, not only what.
