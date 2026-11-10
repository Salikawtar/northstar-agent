# Prompt version log

**Main idea:** every prompt change, why it was made, and its measured effect on the validation chats. The brief's prompting criterion asks for "prompt changes documented with what changed and why".

Rule: change one thing at a time, measure on the 30 validation chats, never on the 40 test chats.

| Prompt | Version | Date | What changed | Why | Validation result |
|---|---|---|---|---|---|
| Router | v1 | 2026-11-10 | First version: role, 10 request types with one-line definitions, escalation rule (D-05), language, confidence, JSON format, 6 invented examples (EN and FR) | Starting point | Haiku 5.5, low effort: type accuracy 80% (24/30), escalation recall 100%, escalation precision 69% (5 false alarms), language 100%, median latency 3.3 s, $0.0003 per chat |
| Router | v2 | 2026-11-10 | (1) out_of_scope now names financing, resale value, plates and general advice, even when a lease or warranty is mentioned; (2) tie-breaks: stuck car = roadside unless a past repair caused it or a manager is demanded; a warning light or recall worry alone is not needs_human; (3) adversarial limited to 5 named tricks, with corrections, writing for a relative and firm requests listed as not adversarial | v1 errors fell in 3 groups: out_of_scope border (v3_0085, v3_0093, v3_0115), safety words over-triggering (v3_0002, v3_0106), corrections flagged as attacks (v3_0114, v3_0115). Rules are written generally, not copied from these chats | To come |

**Error analysis, v1 (Haiku 5.5, low effort).** Wrong type: v3_0009 (needs_human read as roadside: stuck car plus failed brakes plus manager demand), v3_0073 (impersonation inside a warranty topic read as out_of_scope), v3_0085, v3_0093, v3_0115 (out_of_scope border), v3_0106 (brake warning light read as needs_human). False escalations: v3_0002 and v3_0106 (safety words), v3_0111 (firm coverage request read as adversarial), v3_0114 and v3_0115 (a correction and a relative read as adversarial). Labels to double-check with the data owner: v3_0002 and v3_0106, where escalating is arguably reasonable.

**Note on one-change-at-a-time:** v2 bundles three clarifications in one prompt version because each targets a different error group; model and effort stay fixed, so the comparison with v1 is still controlled (prompt only).
