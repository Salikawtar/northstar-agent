# Northstar Motors: Dealership Customer-Support Agent

MMAI 894 Deep Learning, 2026 team project. A bilingual (EN/FR) agent for the
service department of "Northstar Motors", a fictional Ontario dealership group
selling the fictional Meridian brand. All data is synthetic.

## Quick start

Needs Python 3.10 or newer. The full run takes about a minute and needs no key.

```bash
pip install -r requirements.txt
pip install -e .              # lets Python find the project code in src/ (once)
cp .env.example .env          # add your OpenRouter key (only to make NEW model calls)
python run_all.py             # rebuilds the data checks and dealer system, reproduces every key result, runs the tests
```

**No key needed to reproduce the results.** Every model call the team made is recorded in `data/llm_cache/`, so `python run_all.py results` replays the router, the three desks, the full agent, the single-agent baseline, the hand-written chats and the red-team run with the same numbers, at no cost. The key is removed from that stage on purpose, so it can never spend money.

After a prompt or tool change, `python run_all.py record` (with a key) makes only the model calls that are not recorded yet; recorded calls stay free. Then `results` reproduces everything.

## Try the router

```bash
python -m northstar.agent.router --split validation                        # Claude Haiku 5.5
python -m northstar.agent.router --split validation --model compare_small --prompt router/v2.md  # GPT-6 Luna (recorded with prompt v2)
python -m northstar.agent.router --split validation --prompt router/v2.md --effort none  # try a prompt or effort
```
These three runs are recorded in `data/llm_cache/`, so they replay for free with no key. Any other
model, prompt or effort needs `OPENROUTER_API_KEY` in `.env` the first time. Results go to `outputs/results/`.

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

Check the data (free, no model call): diversity in numbers, and the 130 / 30 / 40 split rebuilt and checked for overlap:

```bash
python -m northstar.datagen.diversity
python -m northstar.datagen.split --rebuild
```

Measure the input check (free, no model call):

```bash
python -m northstar.guardrails.evaluate
```

Run the 75 red-team attacks through the whole agent and grade them:

```bash
python -m northstar.guardrails.redteam
```

Final evaluation: 8 setups on the 40 held-out test chats, graded by rules and a model grader, with every table the report uses (replays in about 10 seconds, no key):

```bash
python -m northstar.evaluation                  # or: python run_all.py evaluate
python -m northstar.evaluation consistency      # the grader graded three times: does it agree with itself?
python -m northstar.evaluation check            # the grader against the team's hand labels (percent agreement, Cohen's kappa)
python -m northstar.evaluation --split fresh --setups full_agent single_agent   # the fresh held-out set (D-33): run once after its review and freeze, replayed since
```
Tables in `src/northstar/evaluation/results/`; rubric in `docs/evaluation_rubric.md`; results and error analysis in `docs/evaluation_results.md`. To add a setup to the comparison, add one line to `SETUPS` in `src/northstar/evaluation/setups.py`.

Cost model: a month of chats with people only vs the agent, for each model option, at 1,000 / 100,000 / 1,000,000 chats, with the cost of mistakes and the break-even points (about 5 seconds, no key):

```bash
python -m northstar.economics                   # or: python run_all.py economics
```
Assumptions and their sources in `config/economics.yaml`; results in `src/northstar/economics/results/`; write-ups in `docs/economics.md` (page 7) and `docs/decision_memo.md` (page 1).

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
| `src/northstar/datagen/` | Data-generation pipeline, recorded run and its checks (replay: `python -m northstar.datagen.pipeline`) | Weidi |
| `src/northstar/dms/` | Dealer system generator + tool API (verification enforced in code) | Kawtar |
| `src/northstar/agent/` | Router, specialist agents, single-agent baseline, handoff | Kawtar |
| `src/northstar/guardrails/` | Operating policy, input/output checks, log masking, attack tests | Jessica |
| `src/northstar/finetune/` | Fine-tuned router + small/large prompted baselines | Neeraj |
| `src/northstar/evaluation/` | Setups, harness, rule and model graders, metrics with ranges, error analysis, grader check; committed result tables in `results/` | Libo |
| `src/northstar/economics/` | Cost model, volumes, cost of mistakes, break-even, sensitivity | Abhi |
| `config/economics.yaml` | Every economics assumption, with its source and the range tested | Abhi |
| `prompts/` | Every prompt, versioned (`router/v1.md`...). Changes logged in `docs/prompt_log.md` | Kawtar |
| `config/settings.yaml` | All settings (models, effort, paths, failure injection) | Team |
| `tests/` | Unit tests for every module | Everyone |

Each module folder also holds a reference implementation built by Kawtar.
Teammates' versions plug in through the same contracts, and the evaluation
compares them on the same test set.

## Extend it in an afternoon

| To add | Change | Then |
|---|---|---|
| A tool | Write the function in `src/northstar/dms/store.py`, describe it in `SPECS` and give it to the right desks in `PERMISSIONS` (`src/northstar/agent/tools.py`). A desk that is not listed is refused the tool in code | Add a test in `tests/test_specialist.py` |
| A desk (specialist) | Add a prompt in `prompts/<desk>/v1.md`, a line in `config/settings.yaml` (model tier, reasoning effort, prompt), its tools in `PERMISSIONS`, and its request types in `DESK_FOR` (`src/northstar/agent/specialist.py`) | `python -m northstar.agent.specialist --agent <desk>` |
| A prompt change | Copy the prompt to a new version (`v3.md`), point `config/settings.yaml` at it, log what changed and why in `docs/prompt_log.md` | Run the desk on validation; tune on validation only |
| A rule | Add it to `prompts/shared/` (new version) and to `docs/operating_policy.md`; if it can be checked in code, add a check in `src/northstar/guardrails/` | Add a hand-written chat in `data/handwritten/chats.yaml` |
| A test chat | Add an entry to `data/handwritten/chats.yaml` with the expected result | `python -m northstar.agent.scenarios` |
| An evaluation setup | One line in `SETUPS` (`src/northstar/evaluation/setups.py`) naming the one thing it changes | `python -m northstar.evaluation --setups <name>` |

Where to read first: `docs/architecture.md` (the design), `docs/edge_cases.md` (each edge case, its decision and its test), `docs/decision_log.md` (why), `docs/prompt_log.md` (what each change did).

## Status

| Phase | Status |
|---|---|
| 1. Contracts, repo, mock dealer system | Done |
| 2. Agent (router, specialists, baseline, handoff, failures) | Done: tested on validation, 40 hand-written chats, single-agent comparison |
| 3. Guardrails and attack test set | Built: input and output checks, log masking, red team 75 of 75 resisted, 40 of 40 hand-written chats pass; operating policy P01 to P15 approved by Jessica (`docs/operating_policy.md`) |
| 4. Evaluation and error analysis | Done: 8 setups on the 40 test chats (recommended agent 70% task success by the model grader and 62.5% by the two people who checked it, 18 of 18 handoffs, $5.34 per 1,000 chats), error analysis with 4 fixes (D-32), grader self-consistency, grader checked against two team members' hand labels (kappa 0.71 and 0.77), one run on 31 fresh chats made after the fixes (67.7%, D-33) |
| 5. Fine-tune and 3-model comparison | Done: XLM-RoBERTa vs Haiku vs Sonnet routers on the 40 test chats, break-even volume, data-size study (`src/northstar/finetune/MODEL_CARD.md`). Inside the whole agent the fine-tuned router reaches 40% task success against 70%, so the Haiku router stays |
| 6. Cost model and decision memo | Done: `python run_all.py economics`; recommended agent saves 21% at 20,000 chats a month on the test-chat rates (about 2% on the fresh-set rates), break-even 2,200 chats; gated pilot recommended (`docs/decision_memo.md`) |
| 7. One-command reproduction, final README | Done: `python run_all.py` |

## Rules
- Never commit `.env` or any key.
- Change `contracts.py` only after team agreement; bump `CONTRACT_VERSION`.
- Code comments explain **why**, not only what.
