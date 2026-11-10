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
- **Evidence:** QC_log sheet in `data/source/northstar_synthetic_dataset_v1112.xlsx` (every change with before and after).

### D-05. Escalation rule
- **Date:** 2026-11-10
- **Choice:** `needs_escalation` = True for safety (roadside), bereavement and legal threats (needs_human), every adversarial attempt, and explicit requests for a manager. 73 of 200 chats.
- **Why:** matches the project outline wording ("safety, bereavement, legal threats, adversarial attempts").
- **Alternatives considered:** escalate only manufacturer impersonation and let the agent refuse other attacks on its own (fewer handoffs).
- **Counter-argument:** more chats go to a person (higher human-review cost), and a model trained this way may escalate harmless tricky messages. Watch false escalations in evaluation.

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
- **Evidence:** to come from the router run on the 30 validation chats (accuracy, escalation recall, latency, cost per chat).

### D-08. Router input and fail-safe
- **Date:** 2026-11-10
- **Choice:** the router reads the whole conversation so far and returns one JSON object checked against the shared contract. If the answer is unusable after one correction, the chat goes to a person (`needs_human`, reason `tool_failure`) instead of guessing.
- **Why:** a wrong guess on a safety or attack message is worse than an unnecessary handoff.
- **Prompt:** `prompts/router/v1.md`, with invented examples only, so no dataset chat can leak into the prompt (test `test_prompt_contains_no_dataset_chat`).
