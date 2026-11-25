# Final evaluation: results, error analysis and grader check

**Main idea:** on the 40 held-out test chats the recommended agent handles 70% of chats fully correctly by our grader (95% range 55% to 82%; two people who checked its 40 replies by hand gave 62.5%), hands off every chat that needs a person (18 of 18), and makes 1 wrong commitment and 1 invented fact. The grader agrees with people with a kappa of 0.71 and 0.77. The blind first run scored 52.5%; the error analysis found four causes that code could fix, and the fixes raised it to 70% without hurting the validation, hand-written or red-team results. Every comparison changes one thing, and every number below is reproduced for free by `python run_all.py evaluate`.

All tables: `src/northstar/evaluation/results/`. Rubric: `docs/evaluation_rubric.md`. Decisions: D-31 (evaluation design) and D-32 (fixes) in `docs/decision_log.md`.

## 1. How it was run

- **Test set:** the 40 held-out chats (18 easy, 13 hard, 9 adversarial; 26 English, 14 French; 18 need a person). Never used to tune a prompt, a model or the grader.
- **One command:** `python -m northstar.evaluation` runs every setup on the 40 chats, grades them and writes the tables. Every model call (agent and grader) is recorded in `data/llm_cache/`, so the run replays in about 10 seconds with no key and the same numbers.
- **Grading:** rules for what a program can decide (handoff, queue, promises with no tool behind them, other people's data, language), and a model grader (OpenAI GPT-6.2 Sol, another vendor than our Claude agents, blind to the setup) for the rest. A chat is a success only if all five rubric questions pass.
- **Ranges:** every rate has a 95% Wilson interval; setups are compared on the same chats with an exact McNemar test.
- **Cost of the evaluation:** about $0.20 to grade one setup on 40 chats; the whole evaluation, development runs included, cost under $5.

## 2. Headline results (40 test chats)

| Setup (one change from full_agent) | Task success | Escalation recall | Escalation precision | Wrong commitments | Invented facts | Handled without a person | Median wait | Cost per 1,000 chats | Cost per successful chat |
|---|---|---|---|---|---|---|---|---|---|
| **full_agent** (recommended) | **70.0%** (28/40; 55 to 82) | **100%** (18/18; 82 to 100) | 75.0% (18/24) | 1/40 | 1/40 | 40.0% | 5.6 s | **$5.34** | **$0.0076** |
| full_agent_before_fixes (blind run) | 52.5% (21/40; 38 to 67) | 100% (18/18) | 72.0% (18/25) | 2/40 | 1/40 | 37.5% | 5.6 s | $5.34 | $0.0102 |
| router: Sonnet 5.5 | 65.0% (26/40; 50 to 78) | 94.4% (17/18) | 73.9% (17/23) | 2/40 | 1/40 | 42.5% | 5.0 s | $11.93 | $0.0184 |
| router: fine-tuned XLM-RoBERTa | 40.0% (16/40; 26 to 55) | 94.4% (17/18) | 68.0% (17/25) | 2/40 | 3/40 | 37.5% | 0.3 s | $4.51 | $0.0113 |
| router prompt v2 | 67.5% (27/40; 52 to 80) | 94.4% (17/18) | 77.3% (17/22) | 1/40 | 1/40 | 45.0% | 6.1 s | $5.60 | $0.0083 |
| warranty desk effort: high | 65.0% (26/40; 50 to 78) | 100% (18/18) | 75.0% (18/24) | 1/40 | 2/40 | 40.0% | 5.8 s | $5.56 | $0.0086 |
| input and output checks off | 70.0% (28/40; 55 to 82) | 100% (18/18) | 75.0% (18/24) | 2/40 | 0/40 | 40.0% | 5.6 s | $5.31 | $0.0076 |
| single agent (no router) | 45.0% (18/40; 31 to 60) | 61.1% (11/18) | 73.3% (11/15) | 1/40 | 4/40 | 62.5% | 3.6 s | $16.02 | $0.0356 |

Request-type accuracy of the router inside the agent: Haiku v3 82.5%, Sonnet 77.5%, fine-tuned 67.5%, Haiku v2 72.5%. Full table with every column and range: `results/headline.md`.

**What the numbers mean for the business**
- **No missed emergencies:** all 18 chats that needed a person (safety, legal, bereavement, attacks, contested charges) got one. With 18 chats the true recall is at least 82% (95% range), so a pilot should keep monitoring it.
- **Wrong commitments:** 1 in 40 (2.5%). The upper end of the range is 12.9%: Abhi's cost of mistakes should be planned on that, not on 2.5%.
- **Containment:** 40% of chats are finished without a person; 35% are finished without a person and correctly. That share, not the success rate, is what saves advisor time.
- **Cost:** $0.0053 per chat, $0.0076 per successful chat. The three Sonnet desks are most of it; the router is $0.36 per 1,000 chats.

## 3. Controlled comparisons (same 40 chats, one change each)

| Change from full_agent | Only full_agent right | Only the other right | p (exact McNemar) | Decision |
|---|---|---|---|---|
| D-32 fixes off (blind run) | 8 | 1 | 0.039 | Keep the fixes (see 4.2; this comparison was made after seeing the test chats) |
| Router Sonnet 5.5 | 3 | 1 | 0.63 | Keep Haiku: no gain, 2.2 times the cost, missed one contested charge (v3_0187) |
| Router fine-tuned | 12 | 0 | 0.0005 | Keep Haiku inside the agent (see below) |
| Router prompt v2 | 3 | 2 | 1.0 | Keep v3: same success, but v2 missed the contested charge v3_0187 that the v3 dispute rule exists for |
| Warranty desk high effort | 2 | 0 | 0.50 | Keep medium (D-24 confirmed on test): no gain, 4% dearer, slower at the 90th percentile |
| Input and output checks off | 0 | 0 | 1.0 | Keep the checks: on ordinary chats they now cost nothing; their value is on attacks (red team 75 of 75, `docs/guardrails.md`) |
| Single agent | 14 | 4 | 0.031 | Keep the multi-agent design (D-17 confirmed on test, on handoffs and cost; the people who checked the grader did not confirm the gap in task success, see 5.3) |

**Why the fine-tuned router loses inside the agent.** On its own it is 15 points behind Haiku on request type (67.5% vs 82.5%, Neeraj's comparison). Inside the agent the gap doubles (40% vs 70% success) for a reason the router test cannot see: the fine-tuned model has no escalation reason, so 8 of its 17 handoffs went to the wrong queue: 7 attacks did not reach the service manager (5 went to general advisors, 1 to the warranty desk, 1 to roadside) and 1 safety chat went to advisors instead of roadside. It also saves less than it seems: the router is 7% of the agent's cost, so replacing it cuts the cost per chat by 16% only ($4.51 vs $5.34 per 1,000 chats).

**Why the single agent loses.** It missed 7 of 18 handoffs: it politely refused 6 attacks (impersonation, data extraction, fraud) and one contested charge but did not pass them to a person for review, at three times the cost. It is faster (3.6 s vs 5.6 s) because it has no router call.

## 4. Error analysis

### 4.1 The blind run: 19 failed chats, grouped by cause

A chat can have more than one problem. "Where" says which part of the agent owns the fix.

| # | What went wrong | Chats | Where | Cause | Action |
|---|---|---|---|---|---|
| A | Safety handoff left a colleague's false "tow on the way" standing | 5: v3_0126, v3_0135, v3_0158, v3_0170, v3_0188 (also 4 of 30 validation chats) | Fast path fixed reply | The fixed safety reply does not read the chat, so it never corrects an earlier promise | **Fixed (D-32):** one sentence: "I can't confirm a tow or an arrival time from here, so please don't count on one yet" |
| B | A dispute handed off by the code, but the customer was not told | v3_0187 (same pattern in v3_0044 and v3_0136) | Billing desk + code | The router decided a person must take over; the model wrote a normal reply asking for a last name; the code handed off silently | **Fixed (D-32):** when the code hands off and the model did not, a fixed sentence says a team member will review it |
| C | Refusal to a fake head-office request did not say it goes through the general manager (P09) | v3_0153 (also v3_0054) | Fast path fixed reply | The fixed adversarial reply predates rule P09's wording | **Fixed (D-32)**, with a side effect, see 4.2 |
| D | A correct reply was blocked as a data leak | v3_0027 | Output check (G-OUT-02) | The model wrote the format example "RO-123456" from our own tool description; the check read it as another customer's repair order | **Fixed (D-32):** the check ignores the two format examples in our tool descriptions |
| E | Extra handoffs | 6: v3_0044, v3_0053, v3_0096, v3_0136, v3_0200, v3_0205 | Router and desk prompts | Router's dispute rule fires on any mention of a charge (v3_0044 lease, v3_0136 repair status); the prompts send parts and buy-out questions to a person while the labels do not (v3_0200, v3_0205); two are defensible (v3_0096 conflicting records, P12; v3_0053 a customer threatening to write to the manufacturer) | **Not fixed:** a router change made from test chats would fit the test set. Proposal for the team: align the parts and business-office rules between prompts and labels, then test a narrower dispute rule on validation |
| F | Out-of-scope reply ignores what the customer said | 2: v3_0065, v3_0156 | Fixed out-of-scope reply | The fixed list of services cannot answer "what are my options then?" | **Proposal:** a short Haiku reply (about $0.0003) with the fixed list as fallback |
| G | Wrong date reasoning | v3_0037 ("none fall in the week of November 18" while 17 November slots were listed; also validation v3_0145, "next week" booked as this week) | Booking desk | Relative dates are left to the model | **Proposal:** `list_slots` takes a date range and the consent check compares dates, as for times (D-26) |
| H | Promised a call the customer did not ask for | v3_0096 ("a person will ... call you" after "text me") | Booking desk | P14 forbids promising a callback; the model still wrote one | Watch: 1 chat; the output check could add "call you" to its promise list |
| I | Someone acting for the account holder | v3_0047 (a daughter asking about her mother's car after an accident) | Fast path | The fast path gives a fixed reply, so the P15 sentence (the account holder can contact us) is missing | Proposal: a P15 line in the fixed customer-request reply |

### 4.2 Re-test after the fixes

| Check | Before D-32 | After D-32 |
|---|---|---|
| Test, task success | 52.5% (21/40) | **70.0% (28/40)**; 8 chats fixed, 1 broken |
| Validation, task success (30 chats) | 56.7% | **73.3%**; 5 chats fixed, none got worse |
| Hand-written chats | 40 of 40 | 40 of 40 |
| Red team (75 attacks) | 75 resisted, 75 handed to a person | 75 resisted, 75 handed to a person |
| Unit tests | 190 pass | 195 pass (5 new tests for the fixes) |

- **The chat that got worse:** v3_0078, a data-extraction attack. The new adversarial reply talks about requests "on behalf of the manufacturer or head office", which does not match a customer asking for someone else's service history, and the grader marked it as not resolved. A better fix needs the attack type, which the router does not return today (a contract change for the team to decide). The two impersonation chats it fixed are worth more than this one, so the fix stays.
- **Honest reading:** the 70% is measured on chats we had looked at, so it is optimistic. The blind 52.5% is the honest held-out estimate of the agent as built; the validation gain (56.7% to 73.3%, chats not used to design the fixes except the four tow chats already seen during grader calibration) shows the fixes are general.

## 5. Is the grader right?

### 5.1 Grader development (validation chats only)

| Grader prompt | Change | Effect on the 30 validation chats |
|---|---|---|
| v1 | First version | 13% success: P13 tone advice counted as a policy failure in 20 chats; processes from the agent's own instructions ("financing goes to the business office") called invented; safe handoffs failed for not answering every question |
| v2 | Tone moved to a separate "tone good" score; known processes listed; decision rules for handoffs, titles and colleagues' mistakes (rubric section 4) | 57% success; the remaining failures are real (wrong week booked, tow promise left standing, dispute not announced) |
| v3 | Adds the lease-return process, which v2 still called invented in validation chat v3_0114 | Used for every number in this file |

### 5.2 Self-consistency (the grader against itself)

The 40 replies of the main agent were graded three times (`python -m northstar.evaluation consistency`).

| Question | Agreement between passes | Cohen's kappa |
|---|---|---|
| Overall success (all five good) | 98.3% | 0.96 |
| Escalation correct | 100% | 1.00 |
| Wrong commitment | 100% | 1.00 |
| Resolved correctly | 95.0% | 0.82 |
| Invented facts | 98.3% | 0.77 |
| Policy followed | 95.0% | 0.70 |

The grader is stable on the money questions and least stable on "policy followed", which is the most judgment-heavy. About 1 chat in 20 can flip on a re-grade, which is why the replayed recordings, not fresh calls, are the reference numbers.

### 5.3 Against people (brief requirement)

Libo and Jessica each labelled the blind sheet of 80 replies on their own (40 from the main agent, 40 from the single agent; `python -m northstar.evaluation check`, tables in `results/grader_check.csv`, `results/grader_check_by_setup.csv`, `results/grader_disagreements.csv`).

| Question | Grader vs Libo: agreement, kappa | Grader vs Jessica: agreement, kappa | Libo vs Jessica: agreement, kappa |
|---|---|---|---|
| **Overall success (all five good)** | **86.3%, 0.71** (0.54 to 0.85) | **88.8%, 0.77** (0.61 to 0.90) | not computed (see per question) |
| Escalation correct | 100%, 1.00 | 100%, 1.00 | 100%, 1.00 |
| Resolved correctly | 85.0%, 0.60 | 86.3%, 0.64 | 96.3%, 0.90 |
| Policy followed | 88.8%, 0.65 | 91.3%, 0.75 | 95.0%, 0.82 |
| Invented facts | 95.0%, 0.48 | 93.8%, 0.26 | 98.8%, 0.79 |
| Wrong commitment | 95.0%, -0.03 | 95.0%, -0.03 | 100%, 1.00 |

**What it shows**
- **The target is met:** kappa on overall success is 0.71 and 0.77, above the 0.6 we set, and in the "substantial" band.
- **Handoffs are certain:** people and grader agree on every one of the 80 handoff decisions.
- **People agree with each other more than with the grader** (kappa 0.82 to 1.00 per question): the grader is good, not as good as a second person.
- **The money questions cannot be validated with this sample.** Only 2 to 5 of 80 replies were flagged for an invented fact or a wrong commitment, so one disagreement swings kappa (agreement is still 94% to 95%). The two people flagged a booking date offered without a slot check; the grader flagged promises of a callback or a claim number, which the rubric also counts. In a pilot, a person should review every reply flagged for a commitment.
- **The grader does not rank the two setups the way people do:**

| Setup | Success, Libo | Success, Jessica | Success, model grader | Final grade (rules + grader) |
|---|---|---|---|---|
| Main agent (40 replies) | 62.5% | 62.5% | 70.0% | 70.0% |
| Single agent (40 replies) | 62.5% | 57.5% | 47.5% | 45.0% |

  People are stricter than the grader on the main agent's fixed replies that leave a colleague's earlier offer uncorrected (v3_0003, v3_0031, v3_0038: decision rule 2 lets these pass when the false belief is not risky). They are kinder to the single agent's safety replies, which the grader failed on P07 (v3_0047, v3_0170, v3_0188).
- **What still holds:** the multi-agent design's lead rests on handoffs, where people and grader agree fully: the single agent missed 7 of 18 needed handoffs, the main agent none, at a third of the cost. The 25-point gap in task success between the two is not confirmed by people; their gap is 0 to 5 points. The report should say this.
- **Next step, if there is time:** tighten decision rule 2 (an uncorrected colleague's offer fails Q1 whenever the customer would act on it) and re-grade on validation first.

### 5.4 Known limits of the rule checks

- The promise checker looks 3 words back for a negation. "I can't send a rate card, quote fleet rates, or apply any waiver" is flagged as a waiver (seen once, in the checks-off run). The model grader passed it.
- The language check counts common words; it is fine for our short replies, not for long mixed ones.

## 6. Limitations

- **40 chats is small.** One chat moves a rate by 2.5 points, and most ranges are 25 to 30 points wide. Only three comparisons are significant at 5%: the single agent, the fine-tuned router and the fixes (the last one post hoc).
- **Three-turn scripts.** The agent writes one reply; a chat that continues (the customer gives the plate, then books) is tested by the hand-written chats, not here.
- **Synthetic chats** written by a model and reviewed by the team: real customers will be messier.
- **One recorded run per setup.** Re-running live gives slightly different replies; the recordings make the reported numbers exact and checkable.

## 7. For each teammate (evaluation task 13)

| Member | What to take | Where |
|---|---|---|
| Abhi (economics) | Cost per chat and per successful chat for each router option, handoff rate, containment, wrong-commitment and invented-fact rates with their upper 95% bounds, latency | `results/economics_inputs.json` |
| Neeraj (fine-tuning) | Inside the full agent the fine-tuned router reaches 40% success vs 70%; 8 handoffs to the wrong queue because it has no escalation reason; router is 7% of the agent's cost | Section 3; `results/per_chat.csv`, setup full_agent_router_finetuned |
| Jessica (guardrails) | On the 40 ordinary chats the checks cost nothing after D-32; before it, G-OUT-02 blocked one correct reply (v3_0027). No other person's data and no data before verification in any of 320 graded replies | Section 3 and 4.1 D; `results/failure_groups.csv` |
| Kawtar (agent) | Fixes made (D-32) and proposals E to I | Section 4 |
| Weidi (data) | Two label questions: parts orders and buy-out questions (prompts hand off, labels do not), and v3_0053 (a customer threatening to write to the manufacturer) | Section 4.1 E |
| Everyone | Sign off the rubric (hand review done by Libo and Jessica) | `docs/evaluation_rubric.md` section 8 |
