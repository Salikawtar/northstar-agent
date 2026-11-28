# Fine-tuning study: fine-tuned router against Haiku, Sonnet and Jev

Neeraj's study of the router (report page 4, appendix D7; decision D-36). It replaces the first fine-tuned
router's guessed reason with an attack answer, chooses every setting by cross-validation, and compares four
routers with the same input, the same scoring and the same chats: the fine-tuned XLM-RoBERTa, Claude Haiku 5.5
(the team's router), Claude Sonnet 5.5 and Jev 1.14 (typed questions). Haiku stays the router.

## Check it (no GPU, no key, no cost)

```
pip install -r requirements.txt
pytest tests/test_study_*.py                           # 32 checks, about a minute: rules, scoring, every reported number
python -m northstar.finetune.study.comparison_report   # rebuilds results/comparison/ from the saved predictions
python -m northstar.evaluation --setups full_agent full_agent_router_finetuned_lora full_agent_router_jev
```

The last command runs the whole agent with each router from the recordings (`data/llm_cache/`), like every other
setup. To run the fine-tuned model itself (CPU, about 0.74 s a chat with its five models averaged; first use downloads xlm-roberta-base, 1 GB):

```
pip install -r requirements-finetune.txt
python -m northstar.finetune.study.handover_router "My car won't start and I'm stuck on the highway"
NORTHSTAR_LIVE_FINETUNED=1 python -m northstar.evaluation --setups full_agent_router_finetuned_lora
```

## What is here

| Path | What |
|---|---|
| `protocol.py` | The fixed rules: labels, inputs, folds, the lock on the test and fresh chats (each opening is logged in `results/test_access.log`) |
| `routing.py`, `router_options.py` | The team's handoff rules (copied from the pipeline at 0cc6208, checked by tests) and the router options scored on them |
| `model.py`, `train_cv.py`, `cv_analysis.py` | XLM-RoBERTa with heads for type, person needed, attack and language; 5-fold cross-validation |
| `baselines.py` | Haiku, Sonnet and Jev through OpenRouter, every call recorded; with no key it replays the recordings |
| `final_run.py`, `handover_router.py` | The final run (settings frozen in `config/final_settings.json`) and the trained router as a live model |
| `comparison_report.py` | Every router option and training setup in two tables (`results/comparison/`) |
| `notebooks/` | Steps 01 to 07 as run on Kaggle (T4 GPU for training), with their outputs |
| `results/step08/` | The team repo checked on a clean Kaggle machine (notebook 08): every result replays, every test passes, and the live model makes its recorded decisions |
| `results/` | Cross-validation scores, predictions, recorded calls, the LoRA weights (5 seeds, 1.2 MB each) and the recordings the evaluation replays |
| `docs/EVAL_PROTOCOL.md`, `docs/LAB_NOTES.md` | The rules written before the results, and a note for every step |
| `data/` | The cross-validation folds and the data notes |

## Results in one table (40 test chats, first message)

| | Fine-tuned (LoRA + attack) | Haiku 5.5 | Sonnet 5.5 | Jev 1.14 |
|---|---|---|---|---|
| Request type right | 80.0% | 82.5% | 82.5% | 90.0% |
| Routing step right (person, team, desk) | 87.5% | 90.0% | 90.0% | 87.5% |
| Fresh chats (31): type right | 54.8% | 87.1% | 90.3% | 87.1% |
| Median time per chat | 0.74 s (CPU, five models; 0.15 s for one) | 2.34 s | 1.00 s | 0.46 s |
| Whole agent, task success (test / fresh) | 57.5% / 38.7% | 70.0% / 67.7% | 65.0% / not run | 55.0% / 61.3% |

Sources: `results/step06/final_scores.csv` (time of the fine-tuned router: `results/step08/live_router_check.json`), `src/northstar/evaluation/results/summary.json` and `summary_fresh.json`.
Training and the model calls ran on Kaggle; the notebooks clone the repo and read the key from Kaggle Secrets only.
No key, token or password is stored anywhere in this folder.
