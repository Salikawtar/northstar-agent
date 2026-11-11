# Decision log

**Main idea:** every major choice in the project, in one place: what we chose, why, what else we considered, and what evidence backs it. The brief asks "for every major decision, we want to know what you chose and why". The report (page 3 and appendix) is written from this file.

Add new decisions at the bottom. When results confirm or overturn a decision, add a line under **Evidence** instead of rewriting the entry.

---

### D-01. Problem: a dealership service-department agent
- **Date:** 2026-11 (project outline)
- **Choice:** a bilingual (EN/FR) customer-service agent for Northstar Motors, a fictional Ontario dealership group selling the fictional Meridian brand.
- **Why:** real status quo to compare against (service advisors and a call centre), clear success (request resolved, policy followed), real risks (coverage promises like the Air Canada case, other customers' data), and a narrow subtask to fine-tune (request type and escalation).
- **Alternatives considered:** see the project outline.
- **Evidence:** project outline; brief section "Choosing your problem".

### D-02. Architecture: router plus three specialists
- **Date:** 2026-11-09
- **Choice:** one router and three specialists (booking and status, warranty and recalls, billing and lease), each with only its own tools. A single-agent baseline is kept for comparison.
- **Why:** least privilege (a manipulated booking chat cannot reach invoices), cost (most chats are simple and run on a small model), shorter focused prompts.
- **Alternatives considered:** one agent with all tools. Kept as the baseline.
- **Counter-argument:** more parts, more failure points; a routing error sends the chat to the wrong specialist.
- **Evidence:** to come. We keep multi-agent only if it is at least as accurate and cheaper or safer than the single agent on the same test chats (`docs/architecture.md`, section 4).

### D-03. Verification enforced in code, not in the prompt
- **Date:** 2026-11-09
- **Choice:** plate or repair-order number plus last name, checked by the dealer-system tools. No tool returns personal data without a verified session, and a session only opens one customer's records. No tool exists to approve coverage, waive a fee, refund or assign a loaner.
- **Why:** a prompt can be talked out of a rule; code cannot.
- **Evidence:** tests `test_wrong_name_fails_without_revealing_which_part`, `test_session_cannot_read_another_customers_repair_order`.

### D-04. Synthetic data fixes and hand review (v1110 to v1112)
- **Date:** 2026-11-10
- **Choice:** kept Weidi's 200 chats, fixed what QC found (28 agent replies promising coverage without checking, 14 incoherent chats, 183 em dashes, warranty fraud raised from 5 to 8), then the team reviewed 74 rows by hand (52 kept, 22 fixed) and rewrote all 75 red-team attacks by hand.
- **Why:** criterion 1 "Great" asks for documented quality control with examples of what was fixed, and a test set partly reviewed by hand.
- **Evidence:** QC_log sheet in `data/source/northstar_synthetic_dataset_v1113.xlsx` (every change with before and after).

### D-05. Escalation rule
- **Date:** 2026-11-10
- **Choice:** `needs_escalation` = True for safety (roadside), bereavement and legal threats (needs_human), every adversarial attempt, and explicit requests for a manager. 73 of 200 chats.
- **Why:** matches the project outline wording ("safety, bereavement, legal threats, adversarial attempts").
- **Alternatives considered:** escalate only manufacturer impersonation and let the agent refuse other attacks on its own (fewer handoffs).
- **Counter-argument:** more chats go to a person (higher human-review cost), and a model trained this way may escalate harmless tricky messages. Watch false escalations in evaluation.
- **Update:** extended on 2026-11-11 to billing disputes that contest a charge (D-13); 86 of 200 chats.

### D-06. Splits and branches
- **Date:** 2026-11-10
- **Choice:** train 130 / validation 30 / test 40, grouped by customer. Prompts are tuned on validation only; test is touched once, for the final evaluation. All 11 branches named in the chats were added to the mock dealer system instead of editing the chats.
- **Why:** a validation set stops us from tuning prompts on the test set (inflated results). Grouping by customer stops paraphrases leaking across splits.
- **Evidence:** tests `test_split_sizes`, `test_no_customer_in_two_splits`, `test_every_branch_has_service_slots`.

### D-07. Starting models
- **Date:** 2026-11-10 (prices read from OpenRouter model pages that day)
- **Choice:**
  - small tier (router, booking and status): **Claude Haiku 5.5** (`anthropic/claude-haiku-5.5`), $0.10 / $0.50 per million tokens in / out
  - large tier (warranty and recalls, billing and lease, single-agent baseline): **Claude Sonnet 5.5** (`anthropic/claude-sonnet-5.5`), $2 / $10
  - comparison router from another vendor: **GPT-6 Luna** (`openai/gpt-6-luna`), $0.10 / $0.50
- **Why:** routing is high-volume classification, which small models are built for; Haiku 5.5 is cheap, fast and has an effort setting. Sonnet 5.5 is fast for a large model, and warranty or billing mistakes cost far more than the model. GPT-6 Luna, same price from another vendor, gives a controlled router comparison.
- **Alternatives considered:** GPT-5.6 Luna (twice the price), GPT-6.1 Sol (same price as Sonnet, slower), Gemini 3.8 Flash (cheaper large option, but the price is a temporary 50% discount).
- **Counter-argument:** both main models come from one vendor; French quality is not measured yet.
- **Technical note:** Haiku 5.5 rejects any temperature setting and thinks by default, so the router sends no temperature and uses low reasoning effort.
- **Evidence:** 2026-11-10, router v1 on 30 validation chats with Haiku 5.5: type accuracy 80%, escalation recall 100%, precision 69%, language 100%, $0.0003 per chat (as estimated), median latency 3.3 s (slower than hoped; thinking-off test planned). Recorded answers in `data/llm_cache/` replay the run for free.

### D-08. Router input and fail-safe
- **Date:** 2026-11-10
- **Choice:** the router reads the whole conversation so far and returns one JSON object checked against the shared contract. If the answer is unusable after one correction, the chat goes to a person (`needs_human`, reason `tool_failure`) instead of guessing.
- **Why:** a wrong guess on a safety or attack message is worse than an unnecessary handoff.
- **Prompt:** `prompts/router/v1.md`, with invented examples only, so no dataset chat can leak into the prompt (test `test_prompt_contains_no_dataset_chat`).


### D-09. Router configuration: prompt v2, Claude Haiku 5.5, low effort
- **Date:** 2026-11-10
- **Choice:** router prompt v2 on Claude Haiku 5.5 with low reasoning effort (now the default in `config/settings.yaml`).
- **Why:** best of 4 controlled validation runs: 90% type accuracy, 100% escalation recall and 100% precision, 2.8 s, $0.00036 per chat.
- **Alternatives considered:** thinking off (1.0 s but 73% accuracy and one missed escalation); GPT-6 Luna (3 times cheaper, 67% accuracy, slower).
- **Counter-argument:** 2.8 s per chat is slow for a first step; if latency becomes a problem, the fine-tuned router (Phase 5) is the planned fix, not turning thinking off.
- **Evidence:** `docs/prompt_log.md`, router experiments table; recorded answers in `data/llm_cache/`.

### D-10. Specialist engine: the code decides what was done, not the model
- **Date:** 2026-11-11
- **Choice:** one engine for all three specialists; each differs only by prompt, model and tools (settings and `prompts/`). The model may call tools (max 6 per turn) and then returns a small JSON answer (reply, action, reason, summary). The code then decides: a booking counts only if `book_slot` succeeded; the router's escalation always wins; two failed verifications or two dealer-system failures hand off; promise phrases in the reply ("no charge", "covered", "refund", "loaner") with no tool behind them are recorded as unbacked commitments for the output check.
- **Why:** a model can be talked into saying it did something; the code only counts what the tools confirm. Least privilege twice: a specialist only sees its own tools, and the tool box refuses any other tool in code.
- **Alternatives considered:** let the model fill in commitments and the handoff itself (simpler, but it can be manipulated or forget).
- **Counter-argument:** the promise check is a simple phrase list; it can miss a reworded promise or flag a harmless sentence. It flags for review, it does not edit replies; Jessica's output check is the real gate.
- **Evidence:** tests in `tests/test_specialist.py` (booking backed by tool, other desk's tool refused, tool cap, router escalation wins, verification failures, unbacked promise recorded).

### D-11. Specialist check isolates the specialist from router errors
- **Date:** 2026-11-11
- **Choice:** the development check gives each specialist a router decision built from the gold labels, so its numbers measure the specialist alone. The full pipeline (router plus specialist) is graded by the evaluation module.
- **Why:** if the router is wrong, a bad specialist score would hide where the error came from. Changing one thing at a time.
- **Shared rules:** `prompts/shared/policy_core.md` (P-01 to P-10) is included in every specialist prompt. It is a draft: the rule ids must be aligned with the operating policy owned by the guardrails module.

### D-12. Claim numbers are derived, not random
- **Date:** 2026-11-11
- **Choice:** a warranty claim draft number is computed from the customer and the symptom (`WC-` plus 6 characters of a hash) instead of a random number.
- **Why:** tool results are fed back to the model, so a random number would make every recorded run impossible to replay. Same request, same number; different symptoms still get different numbers.

### D-13. Billing disputes that contest a charge go to the service manager
- **Date:** 2026-11-11 (proposed after the billing specialist's first run; labels confirmed by Kawtar)
- **Choice:** when a customer contests a charge (wants it removed, refunded or corrected), the agent explains what the invoice shows and hands off to the service manager with reason `policy_limit`. A question about a charge ("what is this line?", "what is this card charge?") is answered and not escalated. 13 billing chats were relabelled (11 clear contests, 2 borderline: v3_0140, v3_0152). Escalations: 86 of 200.
- **Why:** the agent has no tool to change an invoice, refund or waive (by design), so a contested charge left with the agent goes nowhere. Money decisions stay with people, as in the project outline's memo.
- **Alternatives considered:** escalate only when the customer asks for a manager (fewer handoffs, labels unchanged), but disputed charges would often be left without an owner.
- **Counter-argument:** more handoffs and advisor time; the line between asking and contesting is a judgement call, which is why the relabelled rows were confirmed by a person and listed in the QC log.
- **Consequences:** router prompt v3 and billing prompt v2 carry the rule; the fine-tune labels change before training.

### D-14. The billing desk may book lease pre-return inspections
- **Date:** 2026-11-11
- **Choice:** the billing and lease specialist gets `list_slots` and `book_slot`, only to book a lease pre-return inspection.
- **Why:** in its first run (v3_0199) it could explain the lease steps but not book the inspection, so a simple request ended in a handoff.
- **Alternatives considered:** pass the booking to the booking specialist (needs a hand-over between agents, more parts) or keep handing off (more advisor time).
- **Counter-argument:** one more tool for that desk widens what a manipulated billing chat could do. The risk is low: browsing slots needs no personal data, and booking needs a verified customer and creates no financial commitment.

### D-15. Fast path: some chats skip the specialist
- **Date:** 2026-11-11
- **Choice:** when the router flags safety, a legal threat, bereavement, a request for a person, a router failure or low confidence (below 0.55), no specialist runs. The customer gets a short fixed reply (English or French) and the chat goes to a person with a summary. A contested charge (policy_limit) or a manipulation attempt (adversarial) still goes to the specialist when the request has a desk, so the customer gets a useful reply before the handoff. Out-of-scope requests get a fixed reply that lists what the dealership can help with.
- **Why:** in these cases a person must act, so a model reply adds cost, delay (a Sonnet reply takes 6 to 9 s) and a chance of saying something wrong. A fixed safety reply always contains the 911 advice.
- **Alternatives considered:** let the specialist write every reply (more personal, slower, riskier); ask one clarifying question when the router is unsure (closer to the original design, but our test chats are single replies and no validation chat was below 0.55).
- **Counter-argument:** a fixed reply ignores details. In the step 5 run the booking specialist repeated the stranded driver's location and phone number back (v3_0069), which reassures the customer; the fixed reply cannot. The person who takes over still sees the whole chat.
