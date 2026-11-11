# Agent tasks tracker

> **Internal working file.** Decide whether to keep or remove it before the repository is shared with the evaluators.

**Main idea:** every task for building the agent (Member 2: agent design, architecture and prompting, 22 marks), what it is, where it feeds into the project, and whether it is done. Design details live in `docs/architecture.md`.

Status values: **Done**, **Designed** (agreed on paper, not yet built), **Partly built**, **To do**.

| # | Task | What it is | Where it is used | Status |
|---|---|---|---|---|
| 1 | Architecture design | Diagram, components, tool permissions, edge cases, handoff and failure rules | Report page 3; guides every build step | Done (`docs/architecture.md`) |
| 2 | Model client | One door for every model call: retries, spending limit, replay cache | Router, specialists, grader; free re-runs for markers | Done (PR #3, `src/northstar/llm.py`) |
| 3 | Choose small and large models | Pick models from measured quality, latency and cost, not guesses | Every component; economics (Abhi); report page 3 | Done (starting choice: Haiku 5.5, Sonnet 5.5, GPT-6 Luna for comparison; `docs/decision_log.md` D-07) |
| 4 | Router | Labels the request (10 types), spots extra requests, decides if a person is needed now, detects the language | First step of every chat; compared with the fine-tuned router (Neeraj) | Done: prompt v3, Haiku 5.5, low effort (83% type accuracy, 100% escalation recall and precision on validation) |
| 5 | Three specialists | Booking and status, warranty and recalls, billing and lease, each with only its own tools | Answers customers; least-privilege evidence for security (Jessica) | Built and run: all three specialists, with the dispute rule and tone rules (results in `docs/prompt_log.md`) |
| 6 | Tool-calling loop | Lets a specialist call dealer-system tools, at most 6 per turn | Specialists and single-agent baseline | Done: max 6 tool calls per turn, own tools only, refused in code otherwise (`src/northstar/agent/tools.py`) |
| 7 | Prompts with the operating policy | Role, numbered policy rules, tool instructions, refusals, examples | Agent behaviour; guardrails cite the same rule ids (Jessica) | Built, to align with Jessica: router v3, booking v1, warranty v1, billing v2, shared rules v2 |
| 8 | Human handoff | Triggers (safety, legal, bereavement, adversarial, manager request...) and the advisor summary | Escalation quality metric (Libo); human-review cost (Abhi) | Built: handoff summary with reason, urgency, queue, masked customer reference (`src/northstar/agent/handoff.py`) |
| 9 | Failure handling | Tool down, broken model output, router unsure: retry once, then a safe reply or a handoff | System design criterion; edge-case tests | Partly built: tools, model client, router fail-safe, specialist fallback, verification and dealer-system failures hand off |
| 10 | Edge cases linked to tests | Each of the 11 edge cases (EC-01 to EC-11) has a design decision and a test | System design criterion ("identified systematically") | Partly built (3 of 11) |
| 11 | Single-agent baseline | One large model with all tools, same test chats | Proves whether the multi-agent design is worth it | To do |
| 12 | Prompt version log | What changed in each prompt version, why, and the measured effect | Prompting criterion ("iteration"); report appendix | Ongoing: router v1 to v3, specialists v1 and v2, shared rules v2 logged with results (`docs/prompt_log.md`) |
| 13 | First run on validation chats | Run the agent on the 30 validation chats; first accuracy, latency and cost | Model and effort choices (task 3); prompt fixes (task 12) | Done: router, the three specialists and the full pipeline (results in `docs/prompt_log.md`) |
| 14 | Hand-off to evaluation | A stable, runnable agent setup in `config/settings.yaml` | Libo's evaluation on the 40 test chats | To do |
| 15 | Report page 3 and appendix | Architecture, model choices, prompt strategy, edge cases, handoff and failure paths; full prompts in the appendix | Final report | To do |
| 16 | Pipeline | Connects router and specialists; fast path straight to a person for safety, legal, bereavement, manager requests (D-15) | The agent Libo evaluates; latency and cost per chat (Abhi) | Built and run on validation: handoff recall 100%, right desk 95%, $0.0085 per chat (`src/northstar/agent/pipeline.py`) |

## Reminder before submission

- [ ] Decide whether to keep or remove this file before sharing the repository with the evaluators.
