# Decision memo (report page 1)

**To:** Northstar Motors leadership (General Manager, Service Director, Finance) · **From:** the Northstar service-chat agent project team (MMAI 894) · **November 2026**

**Decision asked:** approve a one-month pilot of the service-chat agent at three branches, with go / no-go gates.

**Problem.** Advisors and the call centre answer every service chat by hand (bookings, repair status, recalls, warranty, invoices, lease returns, emergencies): about 8.4 minutes of a person's time, or **$2.70 a chat**. After hours nobody answers. A chatbot that promises what it should not is a liability (Air Canada had to honour its chatbot's invented policy in 2024).

**Recommendation: pilot, then scale if the gates are met.** A small model (Claude Haiku 5.5) routes each chat and answers bookings and repair status; a larger model (Claude Sonnet 5.5) handles billing, lease, warranty and recalls, where one wrong promise costs more than thousands of chats. Input and output checks stay on. The agent can never approve a claim, refund, waiver or loaner: it drafts, a person decides. **During the pilot an advisor approves every billing and warranty reply** (one chat in three, about a minute each).

**Results on 40 held-out test chats (English and French, 9 adversarial) and 31 fresh chats (written after every fix, run once):**

| Measure | 40 test chats | 31 fresh chats |
|---|---|---|
| Handled correctly | 70% by the model grader (95% range 55% to 82%), 62.5% by two people on the same replies; 52.5% on the blind first run, before error-analysis fixes | 67.7% (50% to 81%) |
| Finished alone and correctly (saves advisor time) | 35% (22% to 50%) | 3 of 31 (3% to 25%) |
| Needed a person and got one | 18 of 18; 132 of 132 across the four earlier sets | 22 of 24 |
| Red-team attacks resisted | 75 of 75, all passed to a person | 9 of 9 passed to a person |
| Wrong commitments / invented facts | 1 of 40 each, both minor (a promised callback, a wrong date) | none |
| Reply time / model cost | 5.6 s median / $0.017 a chat (under 1% of total cost) | 4.6 s / $0.015 |

**Cost and benefit.** All in (model, people for handed-off chats, servers, engineering, build paid back, and mistakes), a chat costs **$2.08 instead of $2.70** at 100,000 chats a month ($2.15 at 20,000). At about 20,000 chats a month (our estimate) that saves **about $11,000 a month (21%), $133,000 a year**; at 100,000 chats, $62,600 a month (23%). Break-even is **2,200 chats a month**. The pilot (5,000 chats, with approvals) should save about $1,300. At the fresh-chat rates it loses about $1,200 instead and the 21% falls to about 2%, before pricing the two missed handoffs.

**Rejected options.** A Sonnet router cost twice as much and was not better (it missed a contested charge). Our fine-tuned router is ten times faster and nearly free, but inside the agent it finished 10 points fewer chats correctly, which costs 100 times what it saves; it needs more labelled data first. A single all-purpose agent missed 7 of 18 handoffs. Automating warranty approvals loses money if more than 1 in 134 is wrong.

**Key risks.**
- **Rare expensive promises (main risk).** The saving disappears above about **1 expensive wrong promise in 1,400 chats**. We saw none in 185 checks, which only proves the rate is below about 1.6%. Control: advisor approval in the pilot; no tool can approve or refund.
- **A missed handoff.** None in 132 on the earlier sets, 2 of 24 on the fresh chats: the warranty desk asked for identification where a person should have taken over. At our assumed $500 a miss, that outweighs the saving. Control: safety chats get a fixed reply that no model writes; in the pilot every handoff is reviewed and a person approves every warranty reply.
- **Lower containment on real chats.** The case holds down to 14% finished alone. We measured 35% on the test chats but 10% on the fresh ones, where reviewers sent three chats in four to a person. The 25% gate decides.

**Gates after 5,000 pilot chats:** no missed safety or dispute handoff; no expensive promise caught by the approvers; at least 25% finished alone and correctly; minor wrong commitments under 5%. If met, our model gives an **82% chance** that dropping approvals and rolling out to all 11 branches saves money (14% without a pilot). Then keep a 5% review sample and a monthly re-test.

Evidence: pages 2 to 7. Every number is reproduced by `python run_all.py`.
