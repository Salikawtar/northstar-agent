# Guardrails and code quality tasks tracker

> **Internal working file.** Decide whether to keep or remove it before the repository is shared with the evaluators.

**Main idea:** every task for Member 5 (security, guardrails and code quality, 24 marks: 12 + 12), what it is, where it feeds into the project, and whether it is done. **Owner: Jessica.** Kawtar built a reference version of some parts so the agent could be tested; Jessica reviews, owns and extends them. Rules and results: `docs/guardrails.md`.

Status values: **Done**, **Built** (works, to review with Jessica), **Partly built**, **To do**.

| # | Task | What it is | Where it is used | Status |
|---|---|---|---|---|
| 1 | Operating policy | One document: what the agent can say, access, disclose, do and promise, with numbered rules | Report page 6 and appendix; every prompt and check cites its rule ids | Partly built: 10 draft rules (P-01 to P-10) in `prompts/shared/policy_core_v2.md`; the full policy document is to write |
| 2 | Rules in the prompts | The policy rules included in every specialist prompt | First layer of protection | Built (reference): shared rules v2 in every specialist |
| 3 | Input check | Cuts instructions aimed at the assistant, masks card and SIN numbers, cuts very long messages | Layered protection; attack tests | Built (reference): 0 false alarms on 160 normal chats, 8 of 8 dataset injections, 5 of 15 red-team injections (`src/northstar/guardrails/input_check.py`) |
| 4 | Output check | Blocks unbacked promises, other people's data and prompt leaks; removes rule ids | Layered protection; "no invented facts" metric (Libo) | Built (reference): no false blocks on recorded replies (`src/northstar/guardrails/output_check.py`) |
| 5 | Least-privilege tools | Each desk only gets its own tools; any other tool is refused in code | Security criterion; architecture page | Done (`src/northstar/agent/tools.py`) |
| 6 | Identity check in code | Last name plus plate or repair order before any personal data; every identifier must match; a retry cannot drop one | Prevents unauthorized disclosure | Done (`src/northstar/dms/store.py`, D-19) |
| 7 | Data minimisation | Collect only what the task needs; mask what the agent never needs | Sensitive-data handling (report page 6) | Partly built: the agent asks only for last name and plate or repair order; card and SIN numbers masked on input |
| 8 | Log masking | Mask VINs and phone numbers before anything is written to results files and logs | Outline promise ("masks VINs and phone numbers in logs"); report page 6 | To do: results CSVs and the replay cache keep the raw (fake) chat text |
| 9 | No invented policies or unapproved actions | Facts only from tools, no promises without a tool, decisions made in code | Policy failure metric (Libo); wrong-commitment cost (Abhi) | Built: rules P-03 and P-04, output check G-OUT-01, code decides bookings, claims and handoffs |
| 10 | Red-team run | The 75 attacks (5 types, 15 each) through the whole agent, with the red-team customers loaded in the dealer system | Adversarial pass rates (report page 6); residual risks | To do (next): runner to build, about $0.75 to run |
| 11 | Red-team grading | Judge each reply against the attack's "fails if" rule: rules first, a model grader where words matter | Pass and fail rates per attack type | To do (with task 10) |
| 12 | Residual vulnerabilities | What still gets through, why, and the mitigation | Report page 6 ("report residual vulnerabilities honestly") | To do (after task 10) |
| 13 | Repository organisation | Modular folders, clear names, configuration separate from code | Code quality criterion | Built: `src/northstar/` by module, `config/settings.yaml`, `prompts/` versioned; to review with Jessica |
| 14 | Secrets never committed | `.env.example`, `.gitignore`, key read from the environment; check the git history | Code quality criterion | Partly built: `.env.example` and `.gitignore` in place; history check to do |
| 15 | README | Setup, how to run the agent, one command for the evaluation | Newcomer-friendly README (criterion) | Partly built: setup and every run command; the single evaluation command waits for Libo's harness |
| 16 | Clean-repository test | Fresh clone, install, run every command in replay mode with no key | "All components can be reproduced" | To do |
| 17 | Test suite width | Tests for data, router, specialists, pipeline, guardrails, evaluation, fine-tune | Code quality criterion | Partly built: 146 tests; evaluation and fine-tune tests come with those modules |
| 18 | Everyone can explain their work | Each member walks through their own code | Brief requirement | To do (team) |
| 19 | Report page 6 and appendix | Policy, layered safeguards, data handling, attack method and pass rates, residual risks; full policy and attack results in the appendix | Final report | To do |

## Reminder before submission

- [ ] Decide whether to keep or remove this file before sharing the repository with the evaluators.
