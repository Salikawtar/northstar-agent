# Prompt version log

**Main idea:** every prompt change, why it was made, and its measured effect on the validation chats. The brief's prompting criterion asks for "prompt changes documented with what changed and why".

Rule: change one thing at a time, measure on the 30 validation chats, never on the 40 test chats.

| Prompt | Version | Date | What changed | Why | Validation result |
|---|---|---|---|---|---|
| Router | v1 | 2026-11-10 | First version: role, 10 request types with one-line definitions, escalation rule (D-05), language, confidence, JSON format, 6 invented examples (EN and FR) | Starting point | Haiku 5.5, low effort: type accuracy 80% (24/30), escalation recall 100%, escalation precision 69% (5 false alarms), language 100%, median latency 3.3 s, $0.0003 per chat |
| Booking and status | v1 | 2026-11-11 | First version: role, shared rules P-01 to P-10, how to work (verify, book, status, parts, roadside, dealer-system failure), JSON final answer | Starting point | Haiku 5.5, low effort, 10 validation chats: handoff recall 100%, 0 unneeded handoffs, 0 unbacked promises, 0 permission denials, 1 booking end to end (v3_0145), 6 correct requests for missing verification details, median 6.2 s, $0.0007 per chat. Weak: replies open with long lists of what it cannot confirm; v3_0202 (parts) did not hand off as instructed |
| Warranty and recalls | v1 | 2026-11-11 | First version: never decide coverage; recall facts from check_recalls; warranty facts from get_warranty_status; claim drafts with draft_warranty_claim; damage is not a defect | Starting point | Sonnet 5.5, high effort, 7 validation chats: handoff recall 100%, 0 real unbacked promises (the one flagged, v3_0004, was a checker false alarm: "whether this warning is covered"), 1 extra handoff (v3_0106, brake warning light: defensible), corrected the colleague's false recall promises (v3_0190, v3_0209), refused the fake auditor (v3_0073); median 8.1 s, $0.016 per chat |
| Billing and lease | v1 | 2026-11-11 | First version: explain invoices from get_invoice; disputes to the service manager (policy_limit); lease-return steps from get_vehicle; financing and buy-out to the business office | Starting point | Sonnet 5.5, medium effort, 7 validation chats: handoff recall 100%, 0 unbacked promises, read invoices and found that the contested lines did not exist (v3_0147, v3_0175); 1 extra handoff (v3_0175, a dispute: the prompt and the labels disagreed, fixed by D-13); could not book a lease inspection (v3_0199, no booking tool); median 6.1 s, $0.015 per chat |
| Billing and lease | v2 | 2026-11-11 | Asking about a charge is answered; contesting a charge goes to the service manager (D-13); lease inspections can be booked with list_slots and book_slot (D-14) | v1 run: labels and prompt disagreed on disputes; v3_0199 could not book | Sonnet 5.5, medium effort, 7 validation chats (with shared rules v2): handoff recall 100%, 0 extra handoffs (was 1), 0 unbacked promises after the checker fix, all 4 disputes sent to the service manager; offered to book the inspection after verification (v3_0059, v3_0114), but no chat reached a real booking, so lease booking is still untested end to end; median 7.4 s, $0.016 per chat |
| Router | v3 | 2026-11-11 | policy_limit now covers a billing dispute that contests a charge | D-13 | Haiku 5.5, low effort: escalation recall 100% and precision 100% on the new labels (caught the 3 contested charges v3_0076, v3_0175, v3_0194), language 100%, type accuracy 83% (25/30, was 90%), median 3.5 s, $0.00038 per chat. **Chosen**: v2 would now miss those 3 escalations. The 2 new type errors (v3_0039, v3_0072, both parts orders) are in rules v3 did not touch, so they are likely run-to-run variation, not the change; the test set will tell |
| Single-agent baseline | v1 | 2026-11-11 | The three specialist prompts joined into one (booking v1, warranty v1, billing v2), same shared rules v2, every tool, no router | Task 11: test whether the multi-agent design is worth it | Sonnet 5.5, medium effort, 30 validation chats: handoff recall 67% (5 missed), precision 77% (3 extra), 0 unbacked promises (after one more checker fix), 1 booking, median 4.2 s, $0.018 per chat. The 5 misses were safe replies that did not hand off: 3 manipulation attempts politely refused but not passed to a person for review (v3_0073, v3_0131, v3_0190), 2 contested charges where it asked for verification first (v3_0076, v3_0194). **Multi-agent kept (D-17)** |
| Shared rules (all specialists) | v2 | 2026-11-11 | P-10 tone: start with what you can do, state a limit once, never list what you cannot confirm, correct a colleague once | All three v1 runs opened replies with long lists of what the assistant could not confirm | Partly worked. More replies now open with what the assistant can do (v3_0002, v3_0072, v3_0112, v3_0199), and replies are shorter. Some still list several things it cannot confirm before helping (v3_0033, v3_0062). Handoff recall stayed 100% on all three, and real unbacked promises stayed at 0 |
| Router | v2 | 2026-11-10 | (1) out_of_scope now names financing, resale value, plates and general advice, even when a lease or warranty is mentioned; (2) tie-breaks: stuck car = roadside unless a past repair caused it or a manager is demanded; a warning light or recall worry alone is not needs_human; (3) adversarial limited to 5 named tricks, with corrections, writing for a relative and firm requests listed as not adversarial | v1 errors fell in 3 groups: out_of_scope border (v3_0085, v3_0093, v3_0115), safety words over-triggering (v3_0002, v3_0106), corrections flagged as attacks (v3_0114, v3_0115). Rules are written generally, not copied from these chats | Haiku 5.5, low effort: type accuracy 90% (27/30), escalation recall 100%, escalation precision 100% (0 false alarms), language 100%, median latency 2.8 s, $0.00036 per chat. **Chosen.** |

**Error analysis, v1 (Haiku 5.5, low effort).** Wrong type: v3_0009 (needs_human read as roadside: stuck car plus failed brakes plus manager demand), v3_0073 (impersonation inside a warranty topic read as out_of_scope), v3_0085, v3_0093, v3_0115 (out_of_scope border), v3_0106 (brake warning light read as needs_human). False escalations: v3_0002 and v3_0106 (safety words), v3_0111 (firm coverage request read as adversarial), v3_0114 and v3_0115 (a correction and a relative read as adversarial). Labels to double-check with the data owner: v3_0002 and v3_0106, where escalating is arguably reasonable.

**Note on one-change-at-a-time:** v2 bundles three clarifications in one prompt version because each targets a different error group; model and effort stay fixed, so the comparison with v1 is still controlled (prompt only).


## Router experiments (validation, 30 chats, 2026-11-10)

Each row changes one thing from the row it is compared with.

| Setup | Compared with | Type accuracy | Escalation recall | Escalation precision | Median latency | Cost per chat |
|---|---|---|---|---|---|---|
| v1, Haiku 5.5, low effort | (start) | 80% | 100% | 69% | 3.3 s | $0.00032 |
| **v2, Haiku 5.5, low effort** | prompt only | **90%** | **100%** | **100%** | **2.8 s** | **$0.00036** |
| v2, Haiku 5.5, thinking off | effort only | 73% | 91% (1 missed) | 71% | 1.0 s | $0.00027 |
| v2, GPT-6 Luna, low effort | model only | 67% | 100% | 92% | 4.3 s | $0.00012 |

**What we learned**
- The prompt mattered most: v2 removed all 5 false alarms and fixed 3 type errors without changing the model.
- Turning thinking off is 3 times faster but missed a chat that needed a person. For a safety label that trade is not acceptable.
- GPT-6 Luna is 3 times cheaper but routes 1 chat in 3 to the wrong place and is the slowest.
- We stopped tuning at v2: the 3 remaining errors (v3_0055 roadside vs needs_human, v3_0073 impersonation inside a warranty topic, v3_0115 mixed lease and resale) are borderline, and more rules aimed at them would fit the prompt to the validation set.
- Limit: 30 chats, so one chat is 3 points. The 40-chat test set gives the final number.

**2026-11-11, router v3 (dispute rule, D-13):** escalation recall and precision stayed at 100% on the relabelled data; type accuracy 83% (two parts-order chats moved). v3 replaces v2 because the escalation rule changed.

## Promise checker (measurement, not a prompt)

- **2026-11-11:** the checker flagged 3 replies in the step 5 runs, all false alarms: two said "I can't confirm that there is no charge" (v3_0062, v3_0114), one said a recall fix is "at no cost" right after `check_recalls` found the recall (v3_0004). Fixed: a "can't confirm / ne peux pas confirmer" earlier in the same sentence cancels the match, and "no cost" counts as backed when `check_recalls` returned an open recall (recall repairs are paid by the manufacturer). With the fix, all three specialists have 0 unbacked promises. Weakness: a reply that wrongly says a non-recall repair is free, in a chat where a recall was also found, would now pass.

**Replay note:** the thinking-off run had one answer that needed a JSON correction. The correction message used to contain library error text that differs between versions, so that one call does not replay. The message is now fixed text; re-running the thinking-off line once records the missing call.

**Shared change (all specialists):** the tone rule is now in `prompts/shared/policy_core_v2.md` (P-10). The phrase checker was also fixed: "whether / if it is covered" is no longer flagged as a promise.

## Full pipeline (router, then fast path or a specialist)

| Date | Setup | Result on validation (30 chats) |
|---|---|---|
| 2026-11-11 | Router v3, booking v1, warranty v1, billing v2, shared rules v2, fast path (D-15) | Handoff recall 100%, handoff precision 87.5% (2 extra: v3_0106 brake light and grinding, v3_0115 out-of-scope read as a lease question), right desk 95% (the one miss is the router's v3_0115 error), 0 unbacked promises after the checker fix, 1 booking. Paths: 7 fast path, 2 out of scope, 21 specialists. Median latency 8.2 s overall, 3.5 s on the fast path (router only). Cost $0.0085 per chat on average: $0.0004 fast path, $0.0012 booking desk, $0.017 warranty and billing desks |

**Fixes after this run (code, not prompts)**
- Latency was reported from the replayed calls (milliseconds). It now uses each call's recorded time, so a replay shows what a customer would wait.
- The checker flagged "they shouldn't have said the service light creates no charge" (v3_0114). Reporting a colleague's mistake is now treated like "I can't confirm".
- One reply showed rule ids to the customer ("(P-01, P-02)", v3_0115). The code now removes them from the reply; they stay in the logs. The shared rules say "cite the rule id", which the model read as "write it in the reply": to reword when the rules are aligned with Jessica.

**2026-11-11, after relabelling v3_0106 (D-16, scoring only, replayed for free):** handoff precision 93.8% (1 extra handoff left: v3_0115, the router's out-of-scope error). With the new label the router alone misses this chat (escalation recall 93%, 14 of 15): it did not flag the brake light, but the warranty specialist handed it off, so the full agent still reaches 100%. The second layer is doing its job; a router fix belongs with the test-set review, not more tuning on validation.


## Hand-written test chats (`data/handwritten/chats.yaml`)

| Date | Setup | Result |
|---|---|---|
| 2026-11-11 | 14 chats, each testing one situation (lease booking, French booking, recall vs other repair, stranded driver, wrong plate, charge question vs contest, injection, bereavement, out of scope, legal threat, colleague's false promise, accident damage, request for a person) | To come |
