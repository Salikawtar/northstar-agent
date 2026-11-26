# Data dictionary

## Datasets

| File | Rows | What it is | Used by |
|---|---|---|---|
| `data/conversations/conversations.csv` | 200 | Three-turn chats. `split`: train 130 / validation 30 / test 40, grouped by customer. Labels: `request_type` (10 types), `needs_escalation`. `human_reviewed` = True for the 74 rows the team checked by hand (all test rows included). | Fine-tune (train, validation), evaluation (test), DMS build |
| `data/redteam/redteam_75.csv` | 75 | Single-message attacks, 15 per attack type, 3 tactics each, rewritten by hand by the team. `expected_agent_behaviour` and `fails_if` define pass / fail. PII attacks name a decoy in `target_customer_id`. | Guardrail tests only (never trained on) |
| `data/redteam/dms_*.json` | 40 each | Dealer records for the red-team customers, so attacks pass identity checks and reach the guardrails | DMS build |
| `data/fresh/fresh_chats.csv` | 32 | Fresh held-out set (D-33): written by another model family after every fix, reviewed by two team members (31 kept, 1 rejected, 17 labels corrected), then run once. Same columns as the conversations, plus the generator's own escalation label and the review decision. | Final check only (`python -m northstar.evaluation --split fresh`); DMS build |
| `data/source/northstar_synthetic_dataset_v1114.xlsx` | | Review workbook: human review decisions, QC log (every change with before and after), team decisions | Report data section and appendix |

**Escalation rule** (`needs_escalation` = True): safety (roadside), bereavement and legal threats (needs_human), every adversarial attempt, explicit requests for a manager, and billing disputes that contest a charge (D-13), a brake warning light with grinding (D-16). 87 of 200 chats.

# Mock dealer system (DMS)

**Main idea:** the dealer system is built from Weidi's conversations, so every
name, plate, VIN and repair-order number a customer types in a chat exists in
the system. Red-team customers are added from `data/redteam/`, fresh-set customers from `data/fresh/` (D-33). Regenerate with `python run_all.py dms` (same seed, same data).

Fixed "today" for the mock system: **2026-11-16** (`dms.anchor_date` in settings).

| Table (data/dms/) | Rows | Source | Notes |
|---|---|---|---|
| `customers.json` | 184 | 99 from chats + 25 decoys + 40 red-team customers + 20 fresh-set customers | Decoys never appear in any chat. If the agent reveals one, that is a data leak. |
| `vehicles.json` | 184 | Model and year taken from the chat when mentioned (e.g. "2021 Meridian Halden"), otherwise random | ownership: owned / leased / fleet. Leased if the customer has a lease-return chat. |
| `repair_orders.json` | 159 | RO number from the chat (99), the red-team set (40) or the fresh set (20) | status: checked_in, diagnosing, waiting_customer_approval, waiting_parts, in_repair, ready_for_pickup, closed |
| `invoices.json` | 91 | One per closed repair order | Totals include 13% HST. Status `disputed` for customers with a billing-dispute chat. |
| `recalls.json` | 5 | Fictional campaigns | Matched by model + year range. One has parts not available (tests "recall but no parts"). |
| `warranty_terms.json` | 3 | Fictional terms | basic 3y/60,000 km, powertrain 5y/100,000 km, corrosion 7y. |
| `service_slots.json` | ~990 | Weekdays 8:00 to 16:00, 11 locations | About 35% pre-booked. |

## Assumptions to confirm with the team
- Shop labour rate: **165 CAD/hour** (used for estimates; Abhi may replace it with a sourced figure).
- Locations: the 11 branches customers mention in the chats (Oakville, Mississauga, Ottawa, Scarborough, Vaughan, Brampton, Etobicoke, Markham, Burlington, Richmond Hill, Ajax).
- Recall campaigns and warranty terms are invented for the fictional Meridian brand.

## Verification rule (enforced in code)
Plate **or** repair-order number, **plus** last name. Accents, case, spaces and
dashes are ignored ("St-Laurent" = "st laurent", "CBNY 079" = "cbny079").
Wrong details always return the same message, so a caller cannot tell whether
the plate or the name was wrong.
