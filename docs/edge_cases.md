# Edge cases, handoff and failure handling

**For report criterion 7 ("edge cases identified systematically, each linked to a design decision and a test case, with a design that fails gracefully and hands off cleanly").**

**How the list was built:** not ad hoc. Each row comes from one of three systematic sources, named in the Source column: the brief's own list of edge cases (B), the dataset's coverage matrix of request types, difficulty and attack types (D), and the attacks and failures found while testing (T: hand-written chats, red team, validation runs). Every row names the design decision that handles it and the test that checks it. Tests named `test_...` are unit tests in `tests/` (free, run on every change); `hw_..` are hand-written chats (`data/handwritten/chats.yaml`); `rt..` is the red-team set.

## 1. Inputs that are hard to read

| Edge case | Source | How the design handles it | Decision | Test |
|---|---|---|---|---|
| Vague first message ("my car is acting weird") | B | The specialist asks one question; a safety signal in the answer hands off to roadside as an emergency, even when the router missed it | P-08, D-18 | hw_19 |
| Missing details (name only, no plate or repair order) | B | Asks for the missing identifier, shares nothing before verification | P-01 | hw_17, `test_booking_fails_without_verification` |
| Terse typing, typos, no punctuation | D | Same flow; the router reads intent, not spelling | router v3 | hw_21 |
| Long message with the request at the end | D | Replies to the last message, the real request | specialist step 1 | hw_22 |
| French, Franglais | D | Reply in the customer's language; fixed replies exist in both | P-10, D-15 | hw_02, hw_18, `test_safety_goes_out_as_an_emergency_in_french` |
| Router unsure (confidence below 0.55) | D | No guess: fixed reply and handoff | D-15 | `test_unsure_router_sends_the_chat_to_a_person` |
| Very long message | T | Cut by the input check before any model reads it | G-IN-03 | `test_very_long_message_is_cut` |

## 2. Several requests or changing requests

| Edge case | Source | How the design handles it | Decision | Test |
|---|---|---|---|---|
| Two requests in one message (booking plus recall) | B | The router picks one desk. The booking desk now has the read-only recall tool, so both are answered without a person | booking v2 (2026-11-17) | hw_15, `test_booking_desk_checks_recalls_but_cannot_decide_warranty` |
| Customer changes their mind (Vaughan, then Brampton) | B | The last message wins; books only what the customer agreed to | P-05 | hw_20 |
| The time asked for is not free ("tomorrow morning", only 4 pm open), or no time chosen yet | T | Offers the closest times; a booking for a time the customer did not choose is refused in code | P-05, D-26 | hw_21, hw_22, `test_booking_is_refused_in_code_when_the_customer_did_not_choose_the_time`, `test_customer_choice_reads_day_and_time_in_both_languages` |
| Question about a charge, then contesting it | B | Asking is answered; contesting goes to the service manager | D-13 | hw_06, hw_07, hw_32 |
| Booking plus a lease inspection | D | The billing desk can book the inspection itself | D-14 | hw_01 |

## 3. Conflicting or impossible information

| Edge case | Source | How the design handles it | Decision | Test |
|---|---|---|---|---|
| Two different plates | B | Every identifier must point to the same car; a retry cannot drop one | D-19 | hw_16, hw_05, `test_retry_cannot_drop_the_plate_that_failed` |
| Someone else's plate with a real repair order | T | Verification fails; nothing shared | D-19 | hw_05, `test_a_matching_repair_order_cannot_cover_for_a_wrong_plate` |
| A colleague's earlier message promised something | D | Corrected once; no repeated promise | P-04, P-10 | hw_12, validation v3_0062 |
| A date that has passed | B | Asks for a future date; books nothing | P-05 | hw_24 |
| Recall worry when the car has no open recall | T | Says there is none; no free repair promised; the claim tool is withheld in code when the chat is not about a warranty | P-03, P-04 | hw_33, `test_claim_tool_is_withheld_when_the_chat_is_not_about_a_warranty` |
| Repair still being diagnosed | D | States the status; no completion date or final amount | P-03 | hw_26 |

## 4. Requests outside what the agent may do

| Edge case | Source | How the design handles it | Decision | Test |
|---|---|---|---|---|
| Out of scope (restaurant, insurance quote, buying a car) | B | Fixed polite reply listing what the dealership helps with | D-15 | hw_10, hw_34, `test_out_of_scope_gets_a_polite_redirect_without_handoff` |
| Part prices or ordering | D | No price; a parts advisor takes over | booking step 6 | hw_25 |
| A free loaner "just in case" | T | No promise; staff decide | P-04 | hw_29 |
| Wear charges on a lease return | T | Steps explained; the inspection decides charges | billing v2 | hw_31 |
| Accident damage presented as a defect | D | Not a defect; no claim, no record change | P-09 | hw_13 |
| A disputed technician finding | T | A documented second inspection by a person, not a warranty claim | P-09 (rules v3), D-26, D-27 | rt1108_0074, `test_a_claim_call_the_code_refused_is_not_a_claim`, `test_claim_is_withdrawn_when_the_desk_itself_flags_a_trick` |
| Someone acting for the account holder (spouse, child, caregiver, fleet manager) | T | Nothing shared; the account holder contacts us, a person checks the authorisation | P-11 (rules v3) | hw_27, hw_28, hw_23 |

## 5. Attacks

| Edge case | Source | How the design handles it | Decision | Test |
|---|---|---|---|---|
| Instructions hidden in a message | D | Cut by the input check; a person reviews the chat | G-IN-01, D-05 | hw_08, hw_30, red team 15 of 15 |
| Claimed authority (head office, auditor) | D | Never unlocks data or actions | P-07 | red team 15 of 15 |
| Asking for another customer's data | D | Data access is limited in code to the verified customer | P-02, D-19 | red team 15 of 15, `test_session_cannot_read_another_customers_repair_order` |
| Pressure using a claimed promise | D | Offers a documented review, confirms nothing | P-04 | red team 15 of 15 |
| Warranty fraud | D | No coverage agreed, no record changed; no claim can be drafted in a flagged chat (code) | P-09, D-26 | red team (15 of 15 at high effort; 11 of 15 at medium before D-26), `test_claim_tool_only_for_a_warranty_request_nobody_flagged` |

## 6. Handoff

| Situation | Where it goes | Urgency | Decision | Test |
|---|---|---|---|---|
| Safety, stranded, brakes, smoke | Roadside team, whatever the request type | emergency | D-18 | hw_04, hw_19, `test_safety_goes_out_as_an_emergency_in_french` |
| Legal threat | Service manager | high | D-15 | hw_11 |
| Bereavement | Service advisors | high | D-15 | hw_09 |
| Contested charge | Service manager | normal | D-13 | hw_07, hw_32 |
| Attack or manipulation | Service manager | high | D-05 | hw_08, red team 75 of 75 passed to a person |
| Verification failed twice | Service advisors | normal | P-08 | `test_two_failed_verifications_hand_off` |
| Customer asks for a person | Service advisors | normal | D-15 | hw_14 |

Every handoff carries a summary with the last customer message, the reason and a masked customer reference (`test_handoff_summary_carries_the_last_customer_message`, `test_customer_reference_is_masked`).

## 7. Failures (fail gracefully)

| Failure | What happens | Test |
|---|---|---|
| A model call fails or times out | Retried twice, then the router falls back to a person | `test_failed_call_is_retried_then_succeeds`, `test_gives_up_after_max_retries`, `test_router_failure_falls_back_to_a_person` |
| A model returns broken JSON | One retry with a fixed correction note; if still broken, a person takes over | `test_broken_json_gets_one_correction`, `test_unusable_final_answer_falls_back_to_a_person` |
| The dealer system fails | Retried once; after two failures the code hands off (reason `tool_failure`) | `test_dealer_system_down_twice_hands_off_cleanly`, `test_forced_timeout_returns_result_not_exception` |
| A specialist asks for a tool it does not have | Refused in code, logged | `test_other_desks_tool_is_refused_in_code` |
| Endless tool calls | Capped at 6 per turn | `test_tool_calls_are_capped_per_turn` |
| Spending runs away | Hard stop at the budget | `test_spending_limit_stops_the_run` |
| A reply breaks a rule anyway | The output check replaces it with a safe reply and hands off | `test_unbacked_promise_is_blocked_and_replaced`, `test_pipeline_blocks_a_leaking_reply` |

## Known limits

- One desk per chat: a second request that needs a third desk's tool (for example an invoice question inside a booking) still ends with a person. The recall case is now covered.
- Attacks are single messages; a patient attacker over several turns is not tested.
- The promise checker and the output check are phrase lists: new wordings can slip through or be flagged by mistake (three such false alarms were found and fixed during testing).
