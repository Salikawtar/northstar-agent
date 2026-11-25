# Model card: fine-tuned router (XLM-RoBERTa base)

**Main idea:** a small multilingual model trained on 130 chats does the router's job in about a quarter of a second, on a plain CPU, at no cost per chat. It is less accurate than the prompted routers (67.5% vs 82.5% and 77.5% on request type). But it knows when it is unsure, so inside the agent most of its mistakes go to a person instead of to the wrong specialist.

All numbers come from the files in `results/`. Rebuild the tables with `python -m northstar.finetune.compare`.

## What it does

| Input | Output (`RouterOutput`) |
|---|---|
| The three-turn conversation (customer, agent, customer): the same text the prompted router reads | Request type (10 labels), escalation yes/no, language, confidence |

- **Escalation reason** is not learned, because the dataset has no reason labels. A fixed rule picks the reason that sends the chat to the right queue (`predict.py`).
- **Secondary request types** are not given.

## Data

- Northstar synthetic conversations, dataset v1114: 200 chats, English and French.
- **Train** 130, **validation** 30, **test** 40. The same split as the rest of the project, with no customer on both sides.
- Labels: the 10 request types, whether a person must take over, and language.

## How it was built

| Step | What was done | Split used |
|---|---|---|
| 1. Base model | XLM-RoBERTa base, DistilBERT multilingual and mDeBERTa v3, 2 seeds each, learning rate 2e-5 | Validation |
| 2. Learning rate | 1e-5, 2e-5 and 3e-5 for the best base model, 2 seeds each | Validation |
| 3. Final training | Chosen settings, 5 seeds; the router is the seed with the best validation macro F1 | Validation |
| 4. Escalation cut-off | Chosen per seed on validation with F2 (recall counts twice) | Validation |
| 5. Scoring | Router scored once, with the same script as the prompted routers | Test |

**Selection results (validation, mean of 2 seeds):**

| Base model | Learning rate | Validation macro F1 |
|---|---|---|
| **XLM-RoBERTa base** | **3e-5** | **0.733** |
| XLM-RoBERTa base | 2e-5 | 0.673 |
| XLM-RoBERTa base | 1e-5 | 0.556 |
| DistilBERT multilingual | 2e-5 | 0.473 |
| mDeBERTa v3 base | 2e-5 | not trained (crashed under mixed precision) |

**Training settings:** 30 epochs at most, early stop after 6 epochs without improvement, batch 16, AdamW with warmup and linear decay, weight decay 0.01, dropout 0.2, inputs up to 320 tokens (the longest chat is 282). Loss: the three heads' losses summed. Full log: `results/training_log.json`. Learning curves: `results/learning_curves.png`. Validation loss levels off around epoch 20.

## Results on the 40 test chats

| | Fine-tuned (XLM-R) | Small prompted (Haiku) | Large prompted (Sonnet) |
|---|---|---|---|
| Request type accuracy | 67.5% | **82.5%** | 77.5% |
| 95% range | 52% to 80% | 68% to 91% | 62% to 88% |
| Macro F1 | 0.66 | **0.83** | 0.77 |
| Escalation recall | 88.9% (2 missed) | **100%** | 94.4% (1 missed) |
| Escalation precision | **94.1%** | 85.7% | 89.5% |
| Language | 100% | 100% | 100% |
| Median time per chat | **249 ms** | 2,443 ms | 1,047 ms |
| Cost per 1,000 chats | **$0** | $0.36 | $5.56 |

**Is the gap real?** On the same chats, Haiku was right where the fine-tuned model was wrong 9 times, and the reverse 3 times (paired test p = 0.15). Against Sonnet it was 10 times vs 6 (p = 0.45). With 40 chats, neither gap is statistically clear. The direction is consistent, though, so the prompted routers are probably better.

**One run is partly luck.** The 5 seeds scored 62.5% to 75% on test (mean 68.5%). The router seed was chosen on validation and scored 67.5%.

## Inside the agent

The pipeline sends a chat to a person when the router's confidence is below 0.55 (`agent.router_confidence_floor`). The fine-tuned model's confidence is meaningful: the median is 0.95 when it is right and 0.50 when it is wrong. So the floor catches most of its mistakes.

| On the 40 test chats | Fine-tuned | Haiku | Sonnet |
|---|---|---|---|
| Wrong type that reaches a specialist | **2** | **2** | 4 |
| Missed escalations | 1 | **0** | 1 |
| Chats sent to a person | 22 | 21 | 19 |
| ...of which did not need one | 5 | 3 | **2** |

**What this means:** in the agent, the fine-tuned router does about as well as Haiku on safety: the same number of wrongly routed chats, and one more missed escalation. It sends two more chats to a person that did not need one. This is the router's job, so the business comparison is made here.

## Where it wins and where it loses

- **Wins:** speed (about 4x faster than Sonnet and 10x faster than Haiku), no cost per chat, no external API (the chat never leaves the dealer's server), and the best escalation precision.
- **Loses:** adversarial chats (33% vs 67% Haiku and 78% Sonnet). It was fooled by all 3 manufacturer-impersonation chats and both warranty-fraud chats. Weak types: warranty claim (1 of 4), parts order (1 of 3), recall inquiry and repair status (2 of 4 each).
- **French:** 71% (Haiku 93%, Sonnet 79%), on 14 chats.
- **Best types:** lease-end return (5 of 5, where both prompted routers got 3) and out of scope (4 of 4).

Full tables: `results/comparison_per_class.csv` and `results/comparison_by_slice.csv`.

## Cost

- **Training:** about 1.3 minutes per run on a T4 GPU. All 13 training runs (8 for selection, 5 final) took 16 GPU minutes, about $0.12 at $0.45 per GPU hour, and $0 on free Kaggle.
- **Running:** no cost per chat, but a server must run all month. One small CPU server (AWS c7i.large in Canada, $0.0977 per hour) costs about **$71 a month** and can handle about 5 million chats a month at half load.
- **Prompted routers on the same 40 chats:** Haiku $0.015, Sonnet $0.22.

**When it pays off** (`breakeven.py`, `results/breakeven.csv`):

| Chats per month | Fine-tuned | Haiku | Sonnet |
|---|---|---|---|
| 1,000 | $71 | **$0.36** | $5.56 |
| 100,000 | $71 | **$36** | $556 |
| 1,000,000 | **$71** | $363 | $5,560 |

- **Break-even:** cheaper than Haiku above about **197,000 chats a month**, and cheaper than Sonnet above about 12,800.
- **Sensitivity:** with a 1-year committed price, the break-even with Haiku falls to about 143,000 chats a month. With a second server for redundancy, it rises to about 393,000.
- **What this means:** for a single dealership, the router is a small cost either way (Haiku: $36 a month at 100,000 chats). So the choice should rest on accuracy and safety, not on router cost. Fine-tuning pays off on cost only at the scale of a large dealer group or a manufacturer-wide service.
- **Not included:** people's time to label new chats for retraining, engineering time to run the server, and the cost of mistakes. The economics section (Phase 6) adds these.

## How much data would it need? (`datasize.py`, `results/datasize_curve.png`)

The chosen settings were trained on 25%, 50%, 75% and 100% of the training chats (3 seeds each) and scored on validation only.

| Training chats | 33 | 63 | 97 | 130 |
|---|---|---|---|---|
| Validation accuracy (mean of 3) | 26% | 56% | 68% | 83% |

- **Still climbing fast:** about 28 points each time the data doubles, with no sign of levelling off. The model is clearly limited by data.
- **Validation flatters it:** at 130 chats it matches Haiku on validation (83%), but validation chose its settings. On test it is 15 points behind.
- **Estimate:** if the climb held, about 190 training chats (about 19 per request type) would close the test gap. Curves flatten near the top, so this is a lower bound: plan for a few hundred labelled chats (20 to 50 per type).

## Limits

- **Small data:** 130 training chats, and the data-size study shows accuracy still rising steeply. Two seeds per setting reduce the noise in the choices, but 30 validation chats is a small basis for choosing.
- **Learning rate at the top of the range:** 3e-5 was the highest value tried. A higher one might help a little.
- **mDeBERTa not compared:** it crashed under mixed precision, so it was logged as excluded.
- **Escalation reason** comes from a rule, not from the model.
- **Synthetic data:** results on real customer chats may differ.

## Reproduce

- Training: `kaggle_finetune_run.ipynb` on a free Kaggle T4 (about 45 minutes), or the commands in `README.md`.
- Comparison without a GPU or a key: `python run_all.py finetune`.
- The checkpoint (about 1.1 GB) is not in git.

## Credits

First version and Kaggle exploration: Neeraj. Validation-only selection, same-input and same-scoring comparison, agent integration: Kawtar (decision D-30).
