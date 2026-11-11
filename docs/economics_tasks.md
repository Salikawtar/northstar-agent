# Economics and decision memo tasks tracker

> **Internal working file.** Decide whether to keep or remove it before the repository is shared with the evaluators.

**Main idea:** every task for Member 6 (economics, business case and decision memo, 20 marks), what it is, where it feeds into the project, and whether it is done. **Owner: Abhi.** The model takes its inputs from measured results (Libo, Neeraj, Jessica), not from guesses.

Status values: **Done**, **Partly available**, **To do**.

| # | Task | What it is | Where it is used | Status |
|---|---|---|---|---|
| 1 | Business problem | Service advisors and a call centre answer chats today; what AI changes and where a rules-based bot would be enough | Memo (page 1) and economics (page 7) | To do |
| 2 | Status quo baseline | Advisor time per chat and hourly wage, from a public source | Cost comparison | To do |
| 3 | Measured inputs | Cost per chat per setup, share handled without a person, wrong-commitment rate, handoff rate | Every calculation | Partly available: validation numbers ($0.0085 per chat for the full agent, $0.018 for the single agent, 16 of 30 chats handed off, 0 unbacked promises); final numbers come from the test run |
| 4 | Three model options | Operating cost of small prompted, large prompted and fine-tuned routers | Comparison table (brief requirement) | To do (needs Neeraj's results) |
| 5 | Cost per task | Cost per chat and cost per successfully resolved chat, for each option | Page 7 | To do |
| 6 | Volume scenarios | 1,000, 100,000 and 1,000,000 chats per month | Page 7 table | To do |
| 7 | Full cost list | Model calls, training amortised, hosting and monitoring, retries, human review time, cost of errors | Error-adjusted cost | To do |
| 8 | Cost of mistakes | A wrongly promised repair, loaner or waiver; a missed emergency handoff; goodwill | Risk side of the memo | To do |
| 9 | Break-even points | The volume where automation wins, and the wrong-commitment rate above which automating warranty decisions loses money | Page 7 and the memo | To do |
| 10 | When a bigger model is worth it | For example warranty decisions (one wrong promise costs more than thousands of chats) versus routing and bookings | Recommendation logic | To do |
| 11 | Cost model script | A script and an assumptions file that reproduce every number | GitHub submission | To do (`src/northstar/economics/`) |
| 12 | Decision memo | Page 1 for leadership: problem, recommendation, chosen model, measured results, cost and benefit, risks | Final report | To do |
| 13 | Economics page and appendix | Unit economics, scenarios, error-adjusted cost, break-even; detailed assumptions and sensitivity tables in the appendix | Final report | To do |
| 14 | Final report assembly | Put the report together, check consistency, keep it to 7 pages plus appendix | Final submission | To do |

## Reminder before submission

- [ ] Decide whether to keep or remove this file before sharing the repository with the evaluators.
