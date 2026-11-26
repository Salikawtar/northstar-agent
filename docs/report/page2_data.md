# Page 2. Synthetic data

**Designed before it was generated.** A coverage matrix fixes every cell, then one prompt per job asks for a three-turn chat with that job's request type, difficulty, persona, language and realism controls (a mid-chat correction in 118 chats, fragments in 75, CAPS, typos, writing for someone else). The model writes placeholders such as {plate}, never personal details. Faker fills them afterwards, one seed per customer, so the 99 customers keep the same name, car and plate across chats.

| Dimension | Cells | Chats |
|---|---|---|
| Request type | 10: booking, repair status, warranty, recall, roadside, parts, billing dispute, lease return, out of scope, needs a person | 20 each |
| Difficulty | Easy; hard (boundary, missing detail, several asks); adversarial | 100; 60; 40 |
| Language | English; French, 20 of them mixed with English | 130; 70 |
| Persona | 8: terse typist, angry owner in CAPS, caregiver, fleet manager... | 23 to 27 each |
| Attack type | 5: injection, data extraction, pressure, impersonation, fraud | 8 each |
| Extra test sets | Red team (rewritten by hand); hand-written chats; fresh chats | 75; 40; 31 |

**Quality control: what we fixed.** The log holds every change with its before and after text. 90 of the 200 chats were rewritten, among them 28 agent turns that promised coverage, a refund or a waiver without checking, 14 that did not hold together, 22 found in the hand review and 21 with a date in the past. 197 em dashes were removed and 43 handoff labels changed.

| Before | After |
|---|---|
| "a refund of $984 CAD to the original card is being processed today" (v3_0118) | "Refunds need the service manager's approval, so I've sent it to them as a priority" |
| "the airbag warning at 115,000 km is a warranty item, so no charge" (v3_0117) | "At 115,000 km, an airbag warning light is past the basic warranty limit of 3 years or 60,000 km" |

**What we threw out.** A filter with ten rules and a near-copy check reads every chat. The real rejects: in a live trial with eight small models, 4 of 40 chats failed the filter (3 unfilled placeholders, 1 wrong language) and the rest read as garbled, so that route was dropped. For the fresh set, 8 of 40 jobs returned nothing usable, and the two reviewers rejected 1 of the 32 chats and corrected 17 labels. The 15 rejects logged in the main run were planted to exercise each filter rule: they test the filter, not a model.

**A protected test set.** 130 train, 30 validation and 40 test chats, split by customer: no customer is in two splits, and the closest train and test openings score 0.45 where 0.8 counts as a copy. All 40 test chats were reviewed by hand, and prompts were tuned on validation only. Diversity: about two word pairs in three appear only once (distinct-2 0.64), and 1 pair of chats in 19,900 is more than half alike.

**Limits.** One model (Claude, in a chat session) wrote the 200 chats, which shows in that one similar pair; another family (Gemini) wrote the fresh set. The 200 handoff labels do not apply rule P15: 15 of the 25 chats written for someone else ask for no handoff, while the fresh reviewers added one to 6 such chats. The labels are kept so results stay comparable.
