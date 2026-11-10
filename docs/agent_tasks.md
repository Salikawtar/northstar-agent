# Agent tasks tracker

> **Internal working file.** Decide whether to keep or remove it before the repository is shared with the evaluators.

**Main idea:** every task for building the agent (Member 2: agent design, architecture and prompting, 22 marks), what it is, where it feeds into the project, and whether it is done. Design details live in `docs/architecture.md`.

Status values: **Done**, **Designed** (agreed on paper, not yet built), **Partly built**, **To do**.

| # | Task | What it is | Where it is used | Status |
|---|---|---|---|---|
| 1 | Architecture design | Diagram, components, tool permissions, edge cases, handoff and failure rules | Report page 3; guides every build step | Done (`docs/architecture.md`) |
| 2 | Model client | One door for every model call: retries, spending limit, replay cache | Router, specialists, grader; free re-runs for markers | Done (PR #3, `src/northstar/llm.py`) |
| 3 | Choose small and large models | Pick models from measured quality, latency and cost, not guesses | Every component; economics (Abhi); report page 3 | Done (starting choice: Haiku 5.5, Sonnet 5.5, GPT-6 Luna for comparison; `docs/decision_log.md` D-07) |
| 4 | Router | Labels the request (10 types), spots extra requests, decides if a person is needed now, detects the language | First step of every chat; compared with the fine-tuned router (Neeraj) | Built (PR #5, `src/northstar/agent/router.py`); first live run pending |
| 5 | Three specialists | Booking and status, warranty and recalls, billing and lease, each with only its own tools | Answers customers; least-privilege evidence for security (Jessica) | To do |
| 6 | Tool-calling loop | Lets a specialist call dealer-system tools, at most 6 per turn | Specialists and single-agent baseline | To do |
| 7 | Prompts with the operating policy | Role, numbered policy rules, tool instructions, refusals, examples | Agent behaviour; guardrails cite the same rule ids (Jessica) | Partly built (router prompt `prompts/router/v1.md`) |
| 8 | Human handoff | Triggers (safety, legal, bereavement, adversarial, manager request...) and the advisor summary | Escalation quality metric (Libo); human-review cost (Abhi) | Designed |
| 9 | Failure handling | Tool down, broken model output, router unsure: retry once, then a safe reply or a handoff | System design criterion; edge-case tests | Partly built (tools, model client) |
| 10 | Edge cases linked to tests | Each of the 11 edge cases (EC-01 to EC-11) has a design decision and a test | System design criterion ("identified systematically") | Partly built (3 of 11) |
| 11 | Single-agent baseline | One large model with all tools, same test chats | Proves whether the multi-agent design is worth it | To do |
| 12 | Prompt version log | What changed in each prompt version, why, and the measured effect | Prompting criterion ("iteration"); report appendix | Started (`docs/prompt_log.md`) |
| 13 | First run on validation chats | Run the agent on the 30 validation chats; first accuracy, latency and cost | Model and effort choices (task 3); prompt fixes (task 12) | To do |
| 14 | Hand-off to evaluation | A stable, runnable agent setup in `config/settings.yaml` | Libo's evaluation on the 40 test chats | To do |
| 15 | Report page 3 and appendix | Architecture, model choices, prompt strategy, edge cases, handoff and failure paths; full prompts in the appendix | Final report | To do |

## Reminder before submission

- [ ] Decide whether to keep or remove this file before sharing the repository with the evaluators.
