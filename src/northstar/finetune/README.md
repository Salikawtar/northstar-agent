# Fine-tune (Phase 5): owner Neeraj, integrated by Kawtar

**Main idea:** a small multilingual encoder is trained to do the router's job (request type, escalation, language) and plugged in behind the same `RouterOutput` contract. It is then compared with the small (Haiku) and large (Sonnet) prompted routers on the same 40 test chats, with the same input text and the same scoring code.

## Result in one table (40 test chats)

| | Fine-tuned (XLM-R) | Haiku (prompted) | Sonnet (prompted) |
|---|---|---|---|
| Request type accuracy | 67.5% | 82.5% | 77.5% |
| Escalation recall | 88.9% | 100% | 94.4% |
| Routing step: wrong type reaching a specialist | 2 | 2 | 4 |
| Whole agent: task success (final evaluation) | 40.0% | 70.0% | 65.0% |
| Median time per chat | 249 ms | 2,443 ms | 1,047 ms |
| Cost per 1,000 chats | $0 | $0.36 | $5.56 |

The prompted routers are more accurate on request type, but those gaps are not statistically clear on 40 chats. The confidence floor sends most of the fine-tuned model's mistakes to a person. Inside the whole agent the gap is clear (40% against 70% task success, p = 0.0005): the model gives no escalation reason, so 8 of its 17 needed handoffs went to the wrong queue. The recommended agent keeps the Haiku router. Details, limits and the 5-seed spread are in `MODEL_CARD.md`.

## How it works

1. **Same input as the prompted router.** The model reads the three-turn conversation (customer, agent, customer), built by the same function the prompted router uses (`format_conversation`).
2. **One encoder, three heads.** `model.py`: a shared encoder, with three small heads on the first token: 10 request types, escalation yes/no, English or French.
3. **Every choice on validation.** `train_router.py select` picks the base model and learning rate by mean validation macro F1 over 2 seeds. The 40 test chats are not read (a test checks this).
4. **Several seeds, then test once.** `train_router.py final` trains the chosen settings with 5 seeds. It keeps the seed with the best validation score as the router, and sets the escalation cut-off on validation, favouring recall. Only then is each seed scored on test, to show how much one training run can vary.
5. **Same plug, same scoring.** `predict.py` returns a full `RouterOutput`, so `python -m northstar.agent.router --split test --model finetuned` scores it with exactly the code that scores Haiku and Sonnet. `compare.py` builds every table from those row-level results.

## Run it

Training needs a GPU. The free Kaggle T4 takes about 45 minutes. Open `kaggle_finetune_run.ipynb` on Kaggle (GPU on, Internet on) and run all. Or, on any machine with a GPU:

```bash
pip install -r requirements.txt -r requirements-finetune.txt && pip install -e .
python -m northstar.finetune.train_router select                  # validation only
python -m northstar.finetune.train_router final                   # 5 seeds, saves models/finetuned_router
python -m northstar.agent.router --split test --model finetuned   # official test row (CPU)
python -m northstar.agent.router --split test --model small       # prompted baselines (key the first time,
python -m northstar.agent.router --split test --model large       # then replayed from the recordings)
python -m northstar.finetune.compare --collect                    # three-router tables
```

Without a GPU or a key, `python run_all.py finetune` rebuilds the comparison from the committed results.

## Files

| File | What it is |
|---|---|
| `model.py` | Encoder plus three heads; save and load a checkpoint with its settings |
| `train_router.py` | Step 1 `select` and step 2 `final` |
| `predict.py` | `FinetunedRouter`: the fine-tuned model behind the router plug |
| `compare.py` | Three-router tables, confidence intervals and paired tests |
| `breakeven.py` | Monthly volume where the fine-tuned router becomes cheaper (server price in `config/settings.yaml`) |
| `datasize.py` | Learning curve over training-set size: how many chats it would need to match Haiku |
| `kaggle_finetune_run.ipynb` | One-click run on a free Kaggle GPU |
| `kaggle_datasize_run.ipynb` | Data-size runs (25% to 100% of training chats) and LoRA vs full fine-tuning, validation only, about 20 to 25 minutes |
| `MODEL_CARD.md` | What the model is, how it was chosen, results, limits |
| `results/` | Logged outputs: selection runs, seed runs, training log, test results, comparison tables, break-even, data-size and LoRA runs |

The trained checkpoint (about 1.1 GB) is not in git. Retraining takes a few minutes and costs a few cents on a paid GPU.

No API key is used anywhere in this folder.
