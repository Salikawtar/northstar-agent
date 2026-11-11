# Prompt version log

**Main idea:** every prompt change, why it was made, and its measured effect on the validation chats. The brief's prompting criterion asks for "prompt changes documented with what changed and why".

Rule: change one thing at a time, measure on the 30 validation chats, never on the 40 test chats.

| Prompt | Version | Date | What changed | Why | Validation result |
|---|---|---|---|---|---|
| Router | v1 | 2026-11-10 | First version: role, 10 request types with one-line definitions, escalation rule (D-05), language, confidence, JSON format, 6 invented examples (EN and FR) | Starting point | Haiku 5.5, low effort: type accuracy 80% (24/30), escalation recall 100%, escalation precision 69% (5 false alarms), language 100%, median latency 3.3 s, $0.0003 per chat |
| Booking and status | v1 | 2026-11-11 | First version: role, shared rules P-01 to P-10, how to work (verify, book, status, parts, roadside, dealer-system failure), JSON final answer | Starting point | Haiku 5.5, low effort, 10 validation chats: handoff recall 100%, 0 unneeded handoffs, 0 unbacked promises, 0 permission denials, 1 booking end to end (v3_0145), 6 correct requests for missing verification details, median 6.2 s, $0.0007 per chat. Weak: replies open with long lists of what it cannot confirm; v3_0202 (parts) did not hand off as instructed |
| Warranty and recalls | v1 | 2026-11-11 | First version: never decide coverage; recall facts from check_recalls; warranty facts from get_warranty_status; claim drafts with draft_warranty_claim; damage is not a defect | Starting point | To come |
| Billing and lease | v1 | 2026-11-11 | First version: explain invoices from get_invoice; disputes to the service manager (policy_limit); lease-return steps from get_vehicle; financing and buy-out to the business office | Starting point | To come |
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

**Replay note:** the thinking-off run had one answer that needed a JSON correction. The correction message used to contain library error text that differs between versions, so that one call does not replay. The message is now fixed text; re-running the thinking-off line once records the missing call.

**Planned shared change (all specialists):** tone. Lead with what the assistant can do; state a limit once, not as a list. To be made in `prompts/shared/policy_core.md` after all three specialists have a first run, and measured on all of them at once.