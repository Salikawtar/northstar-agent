# Shared contracts (read this before writing code)

**Main idea:** every part of the project passes data in the same fixed shapes.
That is what lets us swap one teammate's module for another and compare them
on the same test cases. The shapes live in `src/northstar/contracts.py`.

Contract version: **1.0.0**. Change it only after the team agrees.

## How data flows

```
customer message
   -> [input guardrail]  -> GuardrailVerdict
   -> [router]           -> RouterOutput        (prompted OR fine-tuned, same shape)
   -> [specialist agent] -> calls tools -> ToolResult (dealer system)
   -> [output guardrail] -> GuardrailVerdict
   -> AgentReply (with HandoffPayload if escalated)
   -> [evaluation]       -> RunRecord, GradeRecord
   -> [economics]        reads RunRecord costs and GradeRecord error rates
```

## The contracts, by owner

| Contract | Produced by | Used by | What it holds |
|---|---|---|---|
| `RouterOutput` | Router (Kawtar prompted / Neeraj fine-tuned) | Agents, evaluation | request type, extra request types, escalate yes/no + reason, confidence, language |
| `ToolResult` | Dealer system tools | Agents | ok or error code, data, latency |
| `AgentReply` | Agents (Kawtar) | Guardrails, evaluation | reply text, action taken, **declared commitments**, tools used, policy rules cited |
| `HandoffPayload` | Agents | Human advisor | reason, urgency, queue, short summary, facts collected |
| `GuardrailVerdict` | Guardrails (Jessica) | Pipeline, evaluation | layer, policy rule id, pass / redact / block / escalate |
| `SetupId`, `RunRecord` | Evaluation runner (Libo) | Evaluation, economics | which setup, tokens, latency, cost per chat |
| `GradeRecord` | Grader (LLM, human or rule) | Evaluation, economics | resolved, policy followed, escalation correct, invented facts, wrong commitment |

## Three rules that matter

1. **Labels come from the dataset.** `RequestType` uses exactly the 10 labels in
   Weidi's file. A test checks this, so the two can never drift apart.
2. **Commitments are declared, not guessed.** If the agent books a slot or
   mentions a price, it must list it in `commitments`. The output guardrail
   then checks each one against policy. Example: a `warranty_coverage`
   commitment is always blocked, because only the warranty desk decides coverage.
3. **Tools never crash.** Every dealer-system call returns a `ToolResult`, even on
   timeout. The agent always has something to respond to.

## Built-in checks

The contracts reject two common model mistakes automatically:
- escalating with no reason (`needs_escalation=true`, reason `none`)
- saying "escalated" with no handoff summary for the human
