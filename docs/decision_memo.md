# Decision memo (report page 1)

**To:** Northstar Motors leadership (General Manager, Service Director, Finance) · **From:** the Northstar service-chat agent project team (MMAI 894) · **November 2026**

**Decision asked:** approve a one-month pilot of the service-chat agent at three branches, with go / no-go gates.

**Problem.** Advisors and the call centre answer every service chat by hand (bookings, repair status, recalls, warranty, invoices, lease returns, emergencies): about 8.4 minutes of a person's time, or **$2.70 a chat**. After hours nobody answers. A chatbot that promises what it should not is a liability (Air Canada had to honour its chatbot's invented policy in 2024).

**Recommendation: pilot, then scale if the gates are met.** A small model (Claude Haiku 5.5) routes each chat and answers bookings and repair status; a larger model (Claude Sonnet 5.5) handles billing, lease, warranty and recalls, where one wrong promise costs more than thousands of chats. Input and output checks stay on. The agent can never approve a claim, refund, waiver or loaner: it drafts, a person decides. **During the pilot an advisor approves every billing and warranty reply** (one chat in three, about a minute each).

**Results on 40 held-out test chats (English and French, 9 adversarial):**

| Measure | Result |
|---|---|
| Handled correctly | 70% (95% range 55% to 82%); 52.5% on the blind first run, before error-analysis fixes |
| Finished alone and correctly (saves advisor time) | 35% (22% to 50%) |
| Needed a person and got one | 18 of 18; 132 of 132 across all test sets |
| Red-team attacks resisted | 75 of 75, all passed to a person |
| Wrong commitments / invented facts | 1 of 40 each, both minor (a promised callback, a wrong date); no money or coverage promise in 185 checks |
| Reply time / model cost | 5.6 s median / $0.017 a chat (under 1% of total cost) |

**Cost and benefit.** All in (model, people for handed-off chats, servers, engineering, build paid back, and mistakes), a chat costs **$2.08 instead of $2.70**. At about 20,000 chats a month (our estimate) that saves **about $11,000 a month (21%), $133,000 a year**; at 100,000 chats, $62,600 a month (23%). Break-even is **2,200 chats a month**. The pilot (5,000 chats, with approvals) should save about $1,300.

**Rejected options.** A Sonnet router cost twice as much and was not better (it missed a contested charge). Our fine-tuned router is ten times faster and nearly free, but inside the agent it finished 10 points fewer chats correctly, which costs 100 times what it saves; it needs more labelled data first. A single all-purpose agent missed 7 of 18 handoffs. Automating warranty approvals loses money if more than 1 in 134 is wrong.

**Key risks.**
- **Rare expensive promises (main risk).** The saving disappears above about **1 expensive wrong promise in 1,400 chats**. We saw none in 185 checks, which only proves the rate is below about 1.6%. Control: advisor approval in the pilot; no tool can approve or refund.
- **A missed urgent handoff.** None in 132, but each is costly. Control: safety chats get a fixed reply that no model writes; every handoff is reviewed in the pilot.
- **Lower containment on real chats.** The case holds down to 14% finished alone (we measured 35%).
- **Grader not yet checked against people.** Two team members will label 80 replies blind.

**Gates after 5,000 pilot chats:** no missed safety or dispute handoff; no expensive promise caught by the approvers; at least 25% finished alone and correctly; minor wrong commitments under 5%. If met, our model gives an **82% chance** that dropping approvals and rolling out to all 11 branches saves money (14% without a pilot). Then keep a 5% review sample and a monthly re-test.

Evidence: pages 2 to 7. Every number is reproduced by `python run_all.py`.
