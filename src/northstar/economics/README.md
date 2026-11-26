# Economics (Phase 6): owner Abhi, reference build Kawtar

**Main idea:** a small, transparent cost model that compares a month of service chats handled by people (today) with the agent, for each model option, at 1,000 / 100,000 / 1,000,000 chats a month. It counts model calls, people, servers, engineering, the build, and the cost of mistakes, then finds the break-even points. Every measured number is read from the evaluation and fine-tune results; every assumption is in `config/economics.yaml` with its source and a range.

## Run it

```bash
python run_all.py economics      # or: python -m northstar.economics
```

No key, no network, about 5 seconds. It reads committed results only.

## How the model works

1. **Today:** chats x 8.4 minutes x advisor cost per minute, plus people's own occasional broken promises.
2. **With the agent, per chat:** model cost (measured cost per reply x 3 replies + 5% retries); people for the 60% handed off; 1.5 chats of a person for the 5% closed wrongly; a 5% review sample; and mistakes (measured rate x cost of one).
3. **Per month:** servers, monitoring, a monthly evaluation run, engineering hours (grow with volume) and the build paid back over 24 months. The fine-tuned option adds its own server (from `finetune/results/breakeven.json`).
4. **Break-even points:** volume, expensive-promise rate, small-mistake rate and containment at which the saving reaches zero; the warranty-approval break-even; the fine-tuned router inside the agent.
5. **Uncertainty:** one-at-a-time sensitivity and 10,000 draws of the measured rates from their Beta posteriors.
6. **Checks beside the base case:** the same agent re-priced with the rates of the fresh held-out set (31 chats, run once), at 20,000 and 100,000 chats and for the pilot month, and the model grader against two people. The base case stays on the 40 test chats; these are shown next to it, not mixed in (`fresh_set_check` and `grader_vs_people` in `results/summary.json`, last two tables of `results/tables.md`).

## Files

| File | What it is |
|---|---|
| `model.py` | The whole model (one file on purpose, so it can be read top to bottom) |
| `results/summary.json` | Every key number used in the memo and page 7 |
| `results/tables.md` | Report tables, generated from the same numbers |
| `results/unit_economics.csv` | Cost per chat and per successful chat, per option |
| `results/scenarios.csv` | Every cost line, per option and volume |
| `results/mistake_costs.csv`, `results/mistakes_seen.csv` | Cost of one mistake; every wrong commitment the grader found, with its severity |
| `results/bigger_model.csv` | When a larger model is worth its cost, part by part |
| `results/sensitivity.csv` | Saving when one assumption moves to its low or high value |
| `results/cost_per_chat_vs_volume.png` | Page 7 figure |

Write-ups: `docs/economics.md` (page 7 and appendix) and `docs/decision_memo.md` (page 1).
