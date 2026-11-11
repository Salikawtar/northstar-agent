# Input and output checks (Phase 3)

**Status:** reference version built by Kawtar on 2026-11-11, **to review with Jessica** (owner of the operating policy and the guardrails). Rule ids P-01 to P-10 are the shared rules in `prompts/shared/policy_core_v2.md`.

**Main idea:** the agent already follows rules in its prompts and in code (verification, tool permissions, handoff). These two checks add a layer before and after the models, written as plain rules: free, instant and predictable. They do not replace the other layers; they catch what slips through.

```
customer message -> INPUT CHECK -> router -> fast path or specialist -> OUTPUT CHECK -> customer
```

Code: `src/northstar/guardrails/input_check.py`, `output_check.py`. Switch: `guardrails.enabled` in `config/settings.yaml`. Every rule that fires is recorded as a `GuardrailVerdict` (layer, rule id, action, detail) and listed in the pipeline results (`guard_flags`).

---

## Input check (before any model)

| Id | Policy | What it catches | Action |
|---|---|---|---|
| G-IN-01 | P-06, P-08 | An instruction aimed at the assistant: "ignore previous instructions", "you are now in admin mode", "system override:", "show me your prompt", and the French equivalents | The instruction is cut out and replaced by a marker, so no model reads it. The rest of the message goes through (the customer may have a real request). A person reviews the chat (reason `adversarial`) |
| G-IN-02 | P-02 | A card number or social insurance number pasted in the chat (checked with the Luhn formula, so ordinary long numbers pass) | Masked before any model or log sees it. Phone numbers and emails are kept: the agent needs them for callbacks |
| G-IN-03 | P-06 | A message longer than 2,000 characters | Cut (limits cost and the room for hidden instructions) |

## Output check (before the customer sees a reply)

| Id | Policy | What it catches | Action |
|---|---|---|---|
| G-OUT-01 | P-04 | A promise no tool backs: coverage, free work, waiver, refund, discount, loaner, an appointment no tool booked | Reply blocked |
| G-OUT-02 | P-02 | A phone number, email, VIN, plate or repair-order number that the customer did not give and no tool returned for the verified customer | Reply blocked, treated as a possible attack |
| G-OUT-03 | P-06 | Pieces of our own instructions (template slots, section titles, output field names) | Reply blocked, treated as a possible attack |
| G-OUT-04 | P-10 | Internal rule ids like "(P-01, P-02)" | Removed from the reply (not blocked) |

**When a reply is blocked:** the customer gets a short safe reply in their language ("I'm passing your request to a team member..."), and the chat goes to a person. The summary says which rule blocked the reply. A data or prompt leak goes to the service manager (`adversarial`); a promise goes to the usual queue (`policy_limit`).

---

## Results (2026-11-11)

**Input check, no model call, free** (`python -m northstar.guardrails.evaluate`)

| Data | Result |
|---|---|
| Dataset, prompt-injection chats | 8 of 8 flagged |
| Dataset, other attacks (fraud, impersonation, pressure, data requests) | 0 of 32 (not its job) |
| Dataset, normal chats | **0 of 160 flagged by mistake** |
| Red team, prompt injection (held out) | **5 of 15 flagged** |
| Red team, the 4 other attack types | 0 of 60 (not its job) |

- The patterns were written from the dataset's injections and general knowledge, never from the red-team set, which stays a held-out test. Looking at the 10 missed red-team injections to add patterns would make that number meaningless.
- 5 of 15 is the honest strength of a phrase list: reworded attacks get through. The end-to-end red-team run will show whether the router, the specialist rules (P-06, P-07) and the output check stop the other 10.

**Full agent with both checks on** (validation, 2026-11-11): same results as before (handoff recall 100%, precision 94%, 0 unbacked promises); the input check flagged the 2 injection chats (v3_0039, v3_0199), the output check blocked nothing; hand-written chats still 14 of 14.

**Output check:** on all recorded replies (30 validation chats, 13 hand-written chats), it blocked **nothing**: no false blocks. Its catches are tested on made-up bad replies (`tests/test_guardrails.py`, 30 tests).

## Known weaknesses (for the review)

- **Phrase lists miss rewordings** (input check) and new ways of making a promise (output check). A small classifier model could replace G-IN-01 later; the end-to-end red-team run will say whether it is needed.
- **Informal French "tu es maintenant..."** is flagged even when harmless (kept as a known false alarm in the tests). No dataset chat uses it.
- **G-OUT-02 compares text.** A number written differently ("905.555.0124" vs "(905) 555-0124") is matched after removing spaces and punctuation, but a plate spelled out in words would pass.
- **Blocking is all or nothing.** A good reply with one bad sentence is fully replaced. Rewriting only the bad sentence would need another model call.

## Questions for Jessica

1. Do the rule ids and actions match the operating policy you are writing? Should G-IN / G-OUT ids live in your policy document?
2. Should a pasted card number also trigger a handoff (fraud risk), or is masking enough?
3. Is "block and hand off" the right action for G-OUT-01, or should a blocked promise get a second try from the specialist first?
