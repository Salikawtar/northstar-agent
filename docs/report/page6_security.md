# Page 6. Security and guardrails

**The policy.** Fifteen written rules (P01 to P15, full table in the appendix) say what the agent may access, say, promise, do and log, each with its reason, what enforces it and the test that checks it. A rule held only by a prompt can be talked around, so the rules that matter are also enforced in code or by a check.

| The agent | Rules | Enforced by, besides the prompt |
|---|---|---|
| Opens only the verified customer's records | P02, P04, P15 | Code: identity check; session bound to one customer |
| Promises only what a tool confirmed | P05, P06, P10 | Code: no tool approves, refunds or edits; output check |
| States record facts; fixed safety wording | P07, P08 | The safety reply is not written by a model |
| Collects and logs the minimum | P03, P11 | Cards and SINs masked on input; phones, emails, VINs and plates masked in results files |
| Obeys no instruction or claimed authority | P09 | Input check cuts it; output check blocks prompt leaks |

**Four layers.** Prompt rules, an input check before any model, tool limits in code, and an output check before the customer. On the 75 red-team attacks, the layer that stopped each one first was a desk's rules (52), the router's fast path (16), the input check (5) or the output check (2).

| Test | Result |
|---|---|
| Red team: 75 attacks, 5 types, 20 in French | 75 of 75 resisted and passed to a person |
| 9 unseen attacks (fresh chats, run once) | 9 of 9 passed to a person; no data shared, no promise; 6 fully correct |
| Input check alone, held-out injections | 5 of 15 flagged; the other 10 stopped further down |
| Normal chats flagged by mistake | 0 of 160 |
| Wrong commitments, invented facts | Test: 1 of 40 each, both minor. Fresh: none in 31 |

**Honest reading.** The 75 of 75 came after several rounds of fixes on these same attacks (it stood at 74 and 71 on the way), so it is not a held-out number. The 9 fresh attacks are held out: all went to a person, but 2 went to the wrong queue and 2 did not say that head-office requests go through the general manager.

**What still gets through.**
- **Rewordings.** The input and output checks are phrase lists; other layers stopped what they missed.
- **Several turns.** Every attack is one message. A patient attacker is not tested.
- **Fleet managers (P15).** A fleet manager is an employee: a person checks the authority. The 40 test labels predate this rule, and in v3_0096 the agent gave one a repair status.
- **Identity.** Last name plus plate is a simulation. A real deployment needs a one-time code or similar.
- **Handoff summaries.** The fast path attaches the customer's last message, so a phone number typed there reaches the advisor unmasked. Results files mask it.
