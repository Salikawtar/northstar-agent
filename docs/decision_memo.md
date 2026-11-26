# Decision memo (report page 1)

**To:** Northstar Motors leadership · **From:** the service-chat agent team (MMAI 894) · **November 2026**

**Problem.** People answer every service chat by hand: about 8.4 minutes, or **$2.70 a chat**. After hours nobody answers. A chatbot that promises what it should not is a liability (Air Canada, 2024).

**Recommendation: a one-month pilot at three branches, then scale if the gates are met.** A small model (Claude Haiku 5.5) routes each chat and answers bookings and repair status; a larger one (Claude Sonnet 5.5) handles billing, lease, warranty and recalls, where one wrong promise costs more than thousands of chats. Input and output checks stay on. The agent never approves a claim, refund, waiver or loaner: it drafts, a person decides. **In the pilot an advisor approves every billing and warranty reply.**

**Results** (95% ranges in brackets; fresh chats written after every fix, run once):

| Measure | 40 held-out test chats | 31 fresh chats |
|---|---|---|
| Handled correctly, by the grader | 70% (55% to 82%); 62.5% by two people | 67.7% (50% to 81%) |
| Finished alone and correctly | 35% (22% to 50%) | 3 of 31 (3% to 25%) |
| Needed a person and got one | 18 of 18 | 22 of 24 |
| Attack chats passed to a person | 75 of 75 red-team, none succeeded | 9 of 9 |
| Wrong commitments, invented facts | 1 of 40 each, both minor | none |

**Cost and benefit.** All in, mistakes included, a chat costs **$2.08 instead of $2.70** at 100,000 chats a month and $2.15 at our 20,000, which saves **about $11,000 a month (21%), $133,000 a year**. Break-even is **2,200 chats a month**. The pilot (5,000 chats) should save about $1,300. At the fresh-chat rates it loses about $1,200 and the 21% falls to about 2%, before pricing the two missed handoffs.

**Key risks.**
- **Rare expensive promises (main risk).** The saving disappears above about **1 expensive wrong promise in 1,400 chats**; none in 185 checks only shows the rate is below about 1.6%. Control: advisor approval in the pilot; no tool can approve or refund.
- **A missed handoff.** None in the 132 earlier cases, 2 of 24 on the fresh chats (the warranty desk asked for identification first). At our assumed $500 a miss, that outweighs the saving. Control: a fixed reply for safety chats; in the pilot every handoff is reviewed and every warranty reply approved.
- **Lower containment on real chats.** The case needs at least 14% finished alone. We measured 35% on the test chats but 10% on the fresh ones, where reviewers sent three chats in four to a person.

**Gates after 5,000 pilot chats:** no missed safety or dispute handoff; no expensive promise caught by approvers; at least 25% finished alone and correctly; minor wrong commitments under 5%. If met, our model gives an **82% chance** that a full rollout without approvals saves money (14% without a pilot).

**Rejected:** a Sonnet router, our fine-tuned router, a single agent, and automated warranty approvals (they lose money if more than 1 in 134 is wrong). Evidence: pages 2 to 7. Every number is reproduced by `python run_all.py`.
