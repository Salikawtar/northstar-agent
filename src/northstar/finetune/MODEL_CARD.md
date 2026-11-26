# Model card: fine-tuned router (XLM-RoBERTa base)

**Main idea:** a small multilingual model trained on 130 chats does the router's job in about a quarter of a second, on a plain CPU, at no cost per chat. It is less accurate than the prompted routers (67.5% vs 82.5% and 77.5% on request type). It knows when it is unsure, so most of its mistakes go to a person instead of to the wrong specialist. That is not enough inside the agent: in the final end-to-end evaluation the agent with this router handles 40% of the test chats correctly, against 70% with Haiku, mainly because the model gives no escalation reason and its handoffs land in the wrong queue.

All numbers come from the files in `results/`. Rebuild the tables with `python -m northstar.finetune.compare`.

## What it does

| Input | Output (`RouterOutput`) |
|---|---|
| The three-turn conversation (customer, agent, customer): the same text the prompted router reads | Request type (10 labels), escalation yes/no, language, confidence |

- **Escalation reason** is not learned, because the dataset has no reason labels. A fixed rule picks a reason from the request type (`predict.py`). The rule cannot say that a chat is an attack, so it does not always pick the right queue (see "Inside the agent").
- **Secondary request types** are not given.

## Data

- Northstar synthetic conversations, dataset v1114: 200 chats, English and French.
- **Train** 130, **validation** 30, **test** 40. The same split as the rest of the project, with no customer on both sides.
- Labels: the 10 request types, whether a person must take over, and language.

## How it was built

| Step | What was done | Split used |
|---|---|---|
| 1. Base model | XLM-RoBERTa base, DistilBERT multilingual and mDeBERTa v3, 2 seeds each, learning rate 2e-5 | Validation |
| 1b. Training method | Full fine-tuning vs LoRA (see below) | Validation |
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

Two views, and they do not say the same thing. The first is computed from the router's own output. The second is the whole agent, graded with the team rubric. The second is the business comparison.

### The routing step alone (router test, `results/comparison_table.csv`)

The pipeline sends a chat to a person when the router's confidence is below 0.55 (`agent.router_confidence_floor`). The fine-tuned model's confidence is meaningful: the median is 0.95 when it is right and 0.50 when it is wrong. So 11 of its 13 type mistakes go to a person (8 of them through the floor) and 2 reach a specialist.

| On the 40 test chats, routing step only | Fine-tuned | Haiku | Sonnet |
|---|---|---|---|
| Wrong type that reaches a specialist | **2** | **2** | 4 |
| Missed escalations | 1 | **0** | 1 |
| Chats sent to a person | 22 | 21 | 19 |
| ...of which did not need one | 5 | 3 | **2** |

**What this shows, and what it cannot:** at the routing step the fine-tuned router looks about as safe as Haiku: the same number of wrongly routed chats, and one more missed escalation. But this table does not check which queue a handoff goes to, or what the customer is told.

### The whole agent (final evaluation, `docs/evaluation_results.md` section 3)

The same 40 chats through the whole agent, with only the router changed (`src/northstar/evaluation/results/summary.json`, setup `full_agent_router_finetuned`).

| On the 40 test chats, whole agent | Fine-tuned router | Haiku router (recommended) | Sonnet router |
|---|---|---|---|
| Task success | 40.0% (16 of 40) | **70.0%** (28 of 40) | 65.0% (26 of 40) |
| Needed handoffs made | 17 of 18 | **18 of 18** | 17 of 18 |
| ...of which reached the right queue | 9 of 17 | **18 of 18** | 16 of 17 |
| Handoffs that were not needed | 8 | 6 | 6 |
| Invented facts | 3 | 1 | 1 |
| Median wait | 0.3 s | 5.6 s | 5.0 s |
| Cost per 1,000 chats | $4.51 | $5.34 | $11.93 |

- **It loses clearly:** the agent with Haiku was right on 12 chats where the agent with the fine-tuned router was wrong, and never the reverse (paired test p = 0.0005). This is the only router gap that is statistically clear on 40 chats.
- **Why:** the reason for a handoff picks the queue. The fine-tuned model gives no reason, and the rule in `predict.py` only knows the request type. So 7 attacks did not reach the service manager (5 went to general advisors, 1 to the warranty desk, 1 to roadside), and 1 safety chat went to advisors instead of roadside.
- **A mistake sent to a person still costs:** 18 chats got a fixed reply and a handoff with no desk involved (12 with Haiku), and 4 of these did not need a person (1 with Haiku). The customer is safe, but the request is not handled.
- **The speed and cost numbers flatter it:** the median wait is 0.3 s because 22 of its 40 chats got a fixed reply that no model writes (16 with Haiku). The cost per chat falls by 16%, but the router is only $0.36 of the $5.34: the rest of the saving is desk calls that did not happen.
- **What this means:** the recommended agent keeps the Haiku router. To be usable, the fine-tuned model would need an escalation-reason head (and reason labels in the data) and more training chats (see the data-size study below).

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
- **Inside the agent it does not pay at any volume today:** the cost model finds it saves $0.0025 a chat in model calls and finishes 10 points fewer chats alone and correctly, which costs about $0.27 a chat in people's time (`docs/economics.md` section 5).
- **Not included:** people's time to label new chats for retraining, engineering time to run the server, and the cost of mistakes. The economics section (Phase 6) adds these.

## Training method: full fine-tuning vs LoRA (`results/lora_summary.json`)

Same base model, data and settings, scored on validation only. LoRA freezes the encoder and trains small add-ons in its attention layers (rank 16 on query and value); its learning rate was chosen from 3e-4 and 1e-3 on validation.

| On 30 validation chats | Full fine-tuning (5 seeds) | LoRA, lr 1e-3 (3 seeds) |
|---|---|---|
| Weights trained | 278 million | 0.6 million (0.2%) |
| Request type accuracy | **78.7%** | 73.3% |
| Macro F1 | **0.75** (± 0.06) | 0.70 (± 0.07) |
| Escalation recall | **93.3%** | 80.0% |
| Minutes per run (T4) | 1.33 | **0.65** |

- **Full fine-tuning kept:** it scored higher on every measure, most clearly on escalation recall, which matters most for safety.
- **The gap is small next to the noise:** the macro F1 difference (0.05) is within one standard deviation across seeds. LoRA is not clearly worse on type, only on escalation.
- **LoRA's real advantages** (half the training time, a checkpoint of a few MB instead of 1.1 GB) do not matter here: a full run already takes about a minute and the model fits easily on a free GPU.
- At learning rate 3e-4, LoRA was still improving at the 30-epoch limit, so that setting was under-trained. At 1e-3 it stopped earlier on its own.

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
- **Escalation reason** comes from a rule, not from the model. In the end-to-end test, 8 of its 17 needed handoffs went to the wrong queue.
- **Synthetic data:** results on real customer chats may differ.

## Reproduce

- Training: `kaggle_finetune_run.ipynb` on a free Kaggle T4 (about 45 minutes), or the commands in `README.md`.
- Comparison without a GPU or a key: `python run_all.py finetune`.
- The checkpoint (about 1.1 GB) is not in git.

## Credits

First version and Kaggle exploration: Neeraj. Validation-only selection, same-input and same-scoring comparison, agent integration: Kawtar (decision D-30).
