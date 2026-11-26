# Page 5. Experiments and evaluation

**What success means.** A reply succeeds only if five things hold, each tied to a business outcome: the request is resolved (no repeat call), the policy is followed (customer data and the dealership's money), the handoff is right (a missed emergency costs most, an extra handoff costs advisor time), nothing is invented, and nothing is promised that only a tool or a person may grant. Code checks what a program can decide; a model grader from another vendor (GPT-6.2 Sol), blind to the setup, judges the rest.

**The test.** 40 held-out chats (9 attacks, 14 in French, 18 needing a person), never used to tune a prompt, a model or the grader. Eight setups, one change each, compared chat by chat with an exact paired test (last column: the chats a setup lost and won against the recommended agent).

| Setup (one change each) | Task success (95% range) | Needed handoffs | Median wait | $ per 1,000 | Lost, won vs agent (p) |
|---|---|---|---|---|---|
| **Recommended agent** | **70.0%** (55 to 82) | **18 of 18** | 5.6 s | **$5.34** | |
| Before the fixes | 52.5% (38 to 67) | 18 of 18 | 5.6 s | $5.34 | 8, 1 (0.039) |
| Router: Sonnet 5.5 | 65.0% (50 to 78) | 17 of 18 | 5.0 s | $11.93 | 3, 1 (0.63) |
| Router: fine-tuned | 40.0% (26 to 55) | 17 of 18 | 0.3 s | $4.51 | 12, 0 (0.0005) |
| Router prompt v2 | 67.5% (52 to 80) | 17 of 18 | 6.1 s | $5.60 | 3, 2 (1.0) |
| Warranty: high effort | 65.0% (50 to 78) | 18 of 18 | 5.8 s | $5.56 | 2, 0 (0.50) |
| Checks off | 70.0% (55 to 82) | 18 of 18 | 5.6 s | $5.31 | 0, 0 (1.0) |
| Single Sonnet agent | 45.0% (31 to 60) | 11 of 18 | 3.6 s | $16.02 | 14, 4 (0.031) |

**Reading it.** No change beats the recommended agent: a Sonnet router, prompt v2 and high warranty effort brought nothing. The agent finishes 35% of chats alone and correctly, the share that saves advisor time (90th-percentile wait 9.0 s). Its 1 wrong promise and 1 invented fact in 40 could each be as high as 12.9%. Three gaps are clear at 5%: the fixes, the fine-tuned router and the single agent, which missed 7 handoffs at three times the cost. The checks do not change success here; see page 6 for attacks.

**Is the grader right?** Two teammates each labelled 80 replies blind. Agreement with the grader on success: kappa 0.71 and 0.77 (target 0.6); on handoffs 100%; the grader with itself over three passes 98.3%. Wrong promises are too rare to check (2 in 80). People gave the agent 62.5%, not 70%, and the single agent 57.5% to 62.5%, not 45%: its lower success is not confirmed, its missed handoffs are.

**Error analysis.** The first, blind run scored 52.5%. Its 19 failures fell into 9 causes, and 4 were fixed in code: a fixed safety reply that left a colleague's false "tow on the way" standing (5 chats), a dispute handed off without telling the customer, a refusal that did not name the general manager, and a correct reply blocked as a data leak. Re-test: 70.0% on test (8 chats fixed, 1 broken), 56.7% to 73.3% on validation, hand-written chats and red team unchanged. Five causes are left, each with a proposal.

**The honest number.** The 70% comes after fixes made on these same chats. So we ran 31 fresh chats once, from another model family, checked by two people: 67.7% (50 to 81), 22 of 24 handoffs, no wrong promise or invented fact. Missed: a contested fee and a fleet manager without proof.

**Limits.** 40 and 31 chats: one chat moves a rate by 2.5 to 3 points. Synthetic three-turn chats.
