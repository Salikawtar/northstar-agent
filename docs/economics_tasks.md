# Economics and decision memo tasks tracker

> **Internal working file.** Decide whether to keep or remove it before the repository is shared with the evaluators.

**Main idea:** every task for Member 6 (economics, business case and decision memo, 20 marks), what it is, where it feeds into the project, and whether it is done. **Owner: Abhi.** The model takes its inputs from measured results (Libo, Neeraj, Jessica), not from guesses.

Status values: **Done**, **Partly available**, **To do**.

| # | Task | What it is | Where it is used | Status |
|---|---|---|---|---|
| 1 | Business problem | Service advisors and a call centre answer chats today; what AI changes and where a rules-based bot would be enough | Memo (page 1) and economics (page 7) | Done: `docs/economics.md` section 1 (40% of test chats end with a fixed reply, where rules are enough for the reply; the model is needed to tell which chat is which, and for the 60% that read records) |
| 2 | Status quo baseline | Advisor time per chat and hourly wage, from a public source | Cost comparison | Done: C$21.50 / h (Job Bank, NOC 64409, Ontario median) + 25% payroll, 8.42 min per chat (LiveChat 2024): $2.70 a chat with people's own mistakes (`config/economics.yaml`) |
| 3 | Measured inputs | Cost per chat per setup, share handled without a person, wrong-commitment rate, handoff rate | Every calculation | Done: read from `src/northstar/evaluation/results/summary.json` by the model, never typed (a test checks it) |
| 4 | Three model options | Operating cost of small prompted, large prompted and fine-tuned routers | Comparison table (brief requirement) | Done: all three routers inside the agent, plus the single agent and the pilot design (`results/unit_economics.csv`); fine-tuned router server from Neeraj's `breakeven.json` |
| 5 | Cost per task | Cost per chat and cost per successfully resolved chat, for each option | Page 7 | Done: model cost $0.017 per chat for the recommended agent; all in $2.08 per chat and $2.97 per successful chat vs $2.70 and $3.85 today |
| 6 | Volume scenarios | 1,000, 100,000 and 1,000,000 chats per month | Page 7 table | Done, plus 20,000 (Northstar size, assumption): -27%, +21%, +23%, +24% (`results/scenarios.csv`, `results/tables.md`) |
| 7 | Full cost list | Model calls, training amortised, hosting and monitoring, retries, human review time, cost of errors | Error-adjusted cost | Done: model calls with retries, people for handoffs and rework, review sample, servers, monitoring, monthly evaluation, engineering, build paid back over 24 months, fine-tuned server and retraining, four kinds of mistakes |
| 8 | Cost of mistakes | A wrongly promised repair, loaner or waiver; a missed emergency handoff; goodwill | Risk side of the memo | Done: $4.73 small mistake, $847 promised repair, $132 loaner, $581 tribunal award, $500 missed handoff (assumption, $100 to $10,000 tested); all 12 wrong commitments seen in 320 test replies were small (`results/mistakes_seen.csv`) |
| 9 | Break-even points | The volume where automation wins, and the wrong-commitment rate above which automating warranty decisions loses money | Page 7 and the memo | Done: 2,200 chats a month; expensive promises 0.074% (1 in 1,350); warranty approvals 0.74% (1 wrong in 134); containment 11% to 14%; fine-tuned router never pays inside the agent |
| 10 | When a bigger model is worth it | For example warranty decisions (one wrong promise costs more than thousands of chats) versus routing and bookings | Recommendation logic | Done: per part, "one avoided mistake pays for N chats" (router 32,000, booking 107, billing 16,000): Haiku for routing and bookings, Sonnet for billing and warranty (confirms D-24, D-25) (`results/bigger_model.csv`) |
| 11 | Cost model script | A script and an assumptions file that reproduce every number | GitHub submission | Done: `src/northstar/economics/model.py` + `config/economics.yaml`; `python run_all.py economics` (5 s, no key); 9 tests in `tests/test_economics.py` |
| 12 | Decision memo | Page 1 for leadership: problem, recommendation, chosen model, measured results, cost and benefit, risks | Final report | Done: `docs/decision_memo.md` (gated pilot at three branches, approval of money replies, go / no-go gates; about 650 words) |
| 13 | Economics page and appendix | Unit economics, scenarios, error-adjusted cost, break-even; detailed assumptions and sensitivity tables in the appendix | Final report | Done: `docs/economics.md` (page 7 sections 1 to 7; appendix A1 assumptions and sources, A2 evidence, A3 sensitivity, A4 uncertainty, A5 limits) |
| 14 | Final report assembly | Put the report together, check consistency, keep it to 7 pages plus appendix | Final submission | Partly done: page plan, sources and consistency checks in `docs/report_plan.md`; pages 1 and 7 ready; pages 2 to 6 to be condensed from their owners' files; the memo's grader line waits for the hand labels |

## Reminder before submission

- [ ] Decide whether to keep or remove this file before sharing the repository with the evaluators.
