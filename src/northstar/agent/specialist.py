"""Specialist engine: the part that talks to the customer.

One engine, three specialists (booking and status, warranty and recalls,
billing and lease). Each one differs only by its prompt, its model and its
tools, all set in config/settings.yaml and prompts/, not in this code.

What happens in one turn:
1. The model reads the conversation and may call tools (at most
   agent.max_tool_calls_per_turn), only its own desk's tools.
2. It returns a small JSON object: the reply, the action and, if a person
   must take over, the reason and a short summary.
3. The code, not the model, decides what counts as a commitment (a booking
   only counts if book_slot succeeded) and whether to hand off (the router's
   escalation decision always wins). The model cannot talk its way out of it.

Quick check on the validation chats of one desk (needs OPENROUTER_API_KEY the
first time, then replays for free):
    python -m northstar.agent.specialist --agent booking_status --split validation
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from northstar.agent.handoff import build_handoff
from northstar.agent.router import format_conversation, load_prompt, resolve_model, turns_from_row
from northstar.agent.tools import ToolBox, result_for_model
from northstar.config import path, settings
from northstar.contracts import (AgentAction, AgentReply, Commitment, CommitmentKind, EscalationReason,
                                 Language, RequestType, RouterOutput)
from northstar.data import load_conversations
from northstar.dms.store import DealerSystem
from northstar.llm import CORRECTION_NOTE, CacheMiss, LLMClient, LLMError

# Which desk handles which request type (docs/architecture.md, section 3).
DESK_FOR: dict[RequestType, str] = {
    RequestType.BOOK_SERVICE: "booking_status", RequestType.REPAIR_STATUS: "booking_status",
    RequestType.PARTS_ORDER: "booking_status", RequestType.ROADSIDE_ASSISTANCE: "booking_status",
    RequestType.WARRANTY_CLAIM: "warranty_recall", RequestType.RECALL_INQUIRY: "warranty_recall",
    RequestType.BILLING_DISPUTE: "billing_lease", RequestType.LEASE_END_RETURN: "billing_lease",
}

TOOL_LIMIT_NOTE = "You have used all the tool calls allowed for this turn. Give your final JSON answer now."


class SpecialistFinal(BaseModel):
    """The model's final answer for this turn, checked before anything is sent."""
    reply: str = Field(min_length=1)
    action: AgentAction
    escalation_reason: EscalationReason = EscalationReason.NONE
    summary: str = ""
    policy_rules_cited: list[str] = Field(default_factory=list)


# Phrases that promise something only a tool or a person may grant. Used to flag
# replies for the output check (Jessica) and for evaluation; it does not edit them.
_PROMISES = [
    (CommitmentKind.WARRANTY_COVERAGE, r"(you'?re covered|is covered|are covered|will be covered|covered under (the )?warranty|est couvert|sont couverts|sera couvert|couvert par la garantie)"),
    (CommitmentKind.FEE_WAIVER, r"(no charge|free of charge|at no cost|for free|waive[ds]?|sans frais|gratuit|gratuitement|annul\w* les frais)"),
    (CommitmentKind.REFUND, r"(we('ll| will) refund|refund (is|has been|will be)|vous serez rembours\w*|remboursement (est|sera))"),
    (CommitmentKind.LOANER, r"(loaner (is|will be|car is)|courtesy car (is|will be)|auto de courtoisie (est|sera)|v[ée]hicule de courtoisie (est|sera))"),
]
_NEGATION = re.compile(r"(not|n't|no|never|pas|aucun|jamais|ni)\W+(\w+\W+){0,3}$", re.I)
# "whether / if it is covered" asks or reports a question, it does not promise.
_QUESTION = re.compile(r"\b(whether|if|si|savoir si|what|ce qui)\W+(\w+\W+){0,4}$", re.I)


# "I can't confirm that there is no charge" reports a limit, it does not promise.
# Checked from the start of the sentence, because the phrase can sit far from the match.
_CANT_CONFIRM = re.compile(
    r"(can'?t|cannot|can not|unable to|not able to|ne (peux|pouvons) pas|impossible de)\s+"
    r"(confirm|promise|guarantee|say|confirmer|promettre|garantir|dire)"
    r"|should(n'?t| not) have (said|told|promised)|was wrong to|n'aurait pas d[uû]|a eu tort", re.I)
# "That message said the repair had no charge" reports what a colleague wrote, it does not promise.
_REPORTED = re.compile(r"\b(message|colleague|coll[eè]gue|they|il|elle)\b[^.!?]{0,40}\b(said|told|stated|a dit|disait|indiquait)\b", re.I)


def _sentence_before(text: str, start: int) -> str:
    cut = max(text.rfind(ch, 0, start) for ch in ".!?\n")
    return text[cut + 1:start]


_RULE_IDS = re.compile(r"\s*\((?:P-\d{2}(?:\s*,\s*|\s+(?:and|et)\s+)?)+\)")


def _strip_rule_ids(text: str) -> str:
    """Rule ids like (P-01, P-02) are for our logs, not for the customer."""
    return _RULE_IDS.sub("", text)


def flag_promises(text: str) -> list[Commitment]:
    out = []
    for kind, pat in _PROMISES:
        for m in re.finditer(pat, text, re.I):
            before = text[max(0, m.start() - 40):m.start()]
            if (not _NEGATION.search(before) and not _QUESTION.search(before)
                    and not _CANT_CONFIRM.search(_sentence_before(text, m.start()))
                    and not _REPORTED.search(_sentence_before(text, m.start()))):
                out.append(Commitment(kind=kind, detail=m.group(0), backed_by_tool=None))
                break
    return out


@dataclass
class TurnResult:
    reply: AgentReply
    latency_ms: float
    cost_usd: float
    input_tokens: int
    output_tokens: int
    tool_calls: int
    denied_tools: list[str] = field(default_factory=list)
    model_calls: int = 0
    verified: bool = False
    error: str = ""


class Specialist:
    def __init__(self, agent: str, client: Optional[LLMClient] = None, model: Optional[str] = None,
                 reasoning_effort: Optional[str] = None, prompt: Optional[str] = None):
        cfg = settings()["components"][agent]
        self.agent = agent
        self.client = client or LLMClient()
        self.model = resolve_model(model or cfg["tier"])
        self.effort = reasoning_effort or cfg.get("reasoning_effort")
        self.max_tokens = cfg.get("max_tokens", 2000)
        self.prompt_name = prompt or cfg["prompt"]
        self.template = load_prompt(self.prompt_name).replace(
            "{policy}", load_prompt(settings()["agent"].get("shared_rules", "shared/policy_core.md")))

    def _system(self, route: RouterOutput, no_router: bool = False) -> str:
        cfg = settings()
        ctx = [f"- Today is {cfg['dms']['anchor_date']}.",
               f"- Branches: {', '.join(cfg['dms']['locations'])}."]
        if no_router:      # single-agent baseline: nobody read the chat before you
            ctx.append("- No one has sorted this chat before you: decide yourself what the customer needs "
                       "and whether a person must take over (rule P-08).")
            return self.template.replace("{context}", "\n".join(ctx))
        ctx += [f"- The router read this chat as: {route.request_type.value}"
               + (f" (also: {', '.join(t.value for t in route.secondary_types)})" if route.secondary_types else "")
               + f"; language {route.language.value}.",
               "- The router decided a person must take over (reason: " + route.escalation_reason.value
               + "). Still reply helpfully and safely, then hand off." if route.needs_escalation
               else "- The router saw no reason to hand off; decide yourself using rule P-08."]
        return self.template.replace("{context}", "\n".join(ctx))

    def run(self, conversation_id: str, turns: list[tuple[str, str]], route: Optional[RouterOutput],
            dms: Optional[DealerSystem] = None, language_hint: Optional[str] = None) -> TurnResult:
        """route=None: no router ran (single-agent baseline). The model decides everything itself;
        the reply is logged with request type needs_human because nobody labelled the chat."""
        no_router = route is None
        if no_router:
            route = RouterOutput(request_type=RequestType.NEEDS_HUMAN, needs_escalation=False, confidence=1.0,
                                 language=Language(language_hint) if language_hint in ("en", "fr") else Language.EN)
        box = ToolBox(dms or DealerSystem(), self.agent)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system(route, no_router)},
            {"role": "user", "content": "Conversation so far:\n" + format_conversation(turns)
             + "\n\nWrite the next Agent reply (use tools first if needed)."}]
        t0 = time.perf_counter()
        cost = 0.0; tin = 0; tout = 0; ncalls = 0; nmodel = 0
        model_wall = 0.0; model_recorded = 0.0   # replayed calls return in ms, so use the recorded time
        final: Optional[SpecialistFinal] = None
        corrected = False
        err = ""
        try:
            while True:
                use_tools = ncalls < box.max_calls()
                tc = time.perf_counter()
                resp = self.client.chat(self.model, messages, reasoning_effort=self.effort, max_tokens=self.max_tokens,
                                        tools=box.specs() if use_tools else None)
                model_wall += time.perf_counter() - tc; model_recorded += resp.latency_ms
                nmodel += 1; cost += resp.cost_usd; tin += resp.input_tokens; tout += resp.output_tokens
                if resp.tool_calls and use_tools:
                    messages.append({"role": "assistant", "content": resp.text or None, "tool_calls": [
                        {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                        for c in resp.tool_calls]})
                    for c in resp.tool_calls:
                        res = box.call(c["name"], c["arguments"]) if ncalls < box.max_calls() else None
                        ncalls += 1
                        content = result_for_model(res) if res else json.dumps({"ok": False, "error": "tool_limit"})
                        messages.append({"role": "tool", "tool_call_id": c["id"], "content": content})
                    if ncalls >= box.max_calls():
                        messages.append({"role": "user", "content": TOOL_LIMIT_NOTE})
                    continue
                try:
                    final = SpecialistFinal.model_validate_json(_strip_fences(resp.text))
                    break
                except (ValidationError, ValueError):
                    if corrected:
                        raise LLMError("final answer still not valid JSON after one correction")
                    corrected = True
                    messages += [{"role": "assistant", "content": resp.text or ""},
                                 {"role": "user", "content": CORRECTION_NOTE}]
        except CacheMiss:
            raise
        except LLMError as e:
            err = str(e)[:300]
        reply = self._decide(conversation_id, route, box, final)
        latency = (time.perf_counter() - t0 - model_wall) * 1000 + model_recorded
        return TurnResult(reply, round(latency, 1), cost, tin, tout, ncalls,
                          list(box.denied), nmodel, box.verified, err)

    def _decide(self, cid: str, route: RouterOutput, box: ToolBox, final: Optional[SpecialistFinal]) -> AgentReply:
        """Code-side rules: what was really done, and whether a person takes over."""
        tools_used = [r.tool for r in box.log]
        booked = next((r for r in box.log if r.tool == "book_slot" and r.ok), None)
        commitments: list[Commitment] = []
        if booked:
            commitments.append(Commitment(kind=CommitmentKind.APPOINTMENT,
                                          detail=f"{booked.data.get('start')} at {booked.data.get('location')}",
                                          backed_by_tool="book_slot"))
        failed_dms = sum(1 for r in box.log if not r.ok and r.error and r.error.value in ("timeout", "unavailable"))

        if final is None:   # model failed: safe reply, a person takes over
            text = ("Désolé, je n'arrive pas à traiter votre demande en ce moment. Un conseiller va vous répondre."
                    if route.language == Language.FR else
                    "Sorry, I can't complete this right now. An advisor will get back to you.")
            reason, summary, action, cited = EscalationReason.TOOL_FAILURE, "The assistant could not produce a valid answer.", AgentAction.ESCALATED, []
        else:
            text, cited = _strip_rule_ids(final.reply), final.policy_rules_cited
            commitments += flag_promises(text)
            # Recall repairs are free for the owner (manufacturer pays), so "no cost" is
            # backed when check_recalls really returned an open recall for this vehicle.
            recall = next((r for r in box.log if r.tool == "check_recalls" and r.ok
                           and (r.data or {}).get("open_recalls")), None)
            if recall:
                for c in commitments:
                    if c.kind == CommitmentKind.FEE_WAIVER and c.backed_by_tool is None:
                        c.backed_by_tool = "check_recalls"
            reason, summary, action = final.escalation_reason, final.summary, final.action
            if route.needs_escalation:                       # the router's decision always wins
                action, reason = AgentAction.ESCALATED, route.escalation_reason
            elif box.verify_failures >= 2:
                action, reason = AgentAction.ESCALATED, EscalationReason.VERIFICATION_FAILED
            elif failed_dms >= 2:
                action, reason = AgentAction.ESCALATED, EscalationReason.TOOL_FAILURE
            elif action == AgentAction.ESCALATED and reason == EscalationReason.NONE:
                reason = EscalationReason.CUSTOMER_REQUEST
            drafted = next((r for r in box.log if r.tool == "draft_warranty_claim" and r.ok), None)
            if action != AgentAction.ESCALATED and booked:
                action = AgentAction.BOOKED
            elif action != AgentAction.ESCALATED and drafted:
                action = AgentAction.DRAFTED_CLAIM
            elif action == AgentAction.DRAFTED_CLAIM and not drafted:
                action = AgentAction.ANSWERED          # the model said it drafted a claim, but no tool did

        handoff = None
        if action == AgentAction.ESCALATED:
            facts = {"verified": str(box.verified)}
            if booked:
                facts["booking"] = commitments[0].detail
            for r in box.log:
                if r.tool == "draft_warranty_claim" and r.ok:
                    facts["warranty_claim_draft"] = r.data.get("claim_id", "")
            handoff = build_handoff(reason, route.request_type, summary or text, box.customer_id, facts)
        return AgentReply(conversation_id=cid, text=text, language=route.language, request_type=route.request_type,
                          action=action, commitments=commitments, tools_used=tools_used,
                          policy_rules_cited=cited, handoff=handoff)


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    # some models add a sentence before the JSON: keep the outermost object
    if not t.startswith("{") and "{" in t:
        t = t[t.index("{"): t.rindex("}") + 1]
    return t.strip()


# ---------------------------------------------------------------------------
# Development check for one desk. The router decision is built from the gold
# labels, so this measures the specialist alone (router errors are measured
# separately). Libo's evaluation module grades the full pipeline in Phase 4.
# ---------------------------------------------------------------------------
def gold_route(row: pd.Series) -> RouterOutput:
    adv = isinstance(row["adversarial_type"], str) and row["adversarial_type"]
    if row["needs_escalation"]:
        reason = (EscalationReason.ADVERSARIAL if adv
                  else EscalationReason.SAFETY if row["request_type"] == "roadside_assistance"
                  else EscalationReason.POLICY_LIMIT if row["request_type"] == "billing_dispute"
                  else EscalationReason.CUSTOMER_REQUEST)
    else:
        reason = EscalationReason.NONE
    return RouterOutput(request_type=RequestType(row["request_type"]), needs_escalation=bool(row["needs_escalation"]),
                        escalation_reason=reason, confidence=1.0, language=Language(row["language"]))


def evaluate(agent: str, split: str = "validation", model: Optional[str] = None, prompt: Optional[str] = None,
             effort: Optional[str] = None, specialist: Optional[Specialist] = None) -> tuple[pd.DataFrame, dict]:
    sp = specialist or Specialist(agent, model=model, prompt=prompt, reasoning_effort=effort)
    df = load_conversations(split)
    df = df[df.request_type.map(lambda t: DESK_FOR.get(RequestType(t)) == agent)]
    rows = []
    for _, r in df.iterrows():
        res = sp.run(r["id"], turns_from_row(r), gold_route(r), DealerSystem())
        rep = res.reply
        unbacked = [c for c in rep.commitments if c.backed_by_tool is None]
        rows.append(dict(
            id=r["id"], request_type=r["request_type"], difficulty=r["difficulty"],
            adversarial_type=r["adversarial_type"] if isinstance(r["adversarial_type"], str) else "",
            gold_escalation=bool(r["needs_escalation"]), action=rep.action.value,
            escalated=rep.action == AgentAction.ESCALATED, handoff_reason=rep.handoff.reason.value if rep.handoff else "",
            verified=res.verified,
            tools=",".join(rep.tools_used), tool_calls=res.tool_calls, denied_tools=",".join(res.denied_tools),
            unbacked_promises=";".join(f"{c.kind.value}: {c.detail}" for c in unbacked),
            rules_cited=",".join(rep.policy_rules_cited), reply=rep.text, model_calls=res.model_calls,
            latency_ms=res.latency_ms, cost_usd=res.cost_usd, error=res.error))
    out = pd.DataFrame(rows)
    n = len(out)
    g = out[out.gold_escalation]
    summary = dict(
        agent=agent, model=sp.model, prompt=sp.prompt_name, reasoning_effort=sp.effort, split=split, n=n,
        handoff_recall=round(g.escalated.mean(), 3) if len(g) else None,          # chats that needed a person and got one
        unneeded_handoffs=int((out.escalated & ~out.gold_escalation).sum()),      # sent to a person without a reason in the labels
        replies_with_unbacked_promise=int((out.unbacked_promises != "").sum()),   # should be 0
        tool_permission_denials=int((out.denied_tools != "").sum()),              # asked for another desk's tool
        bookings_made=int((out.action == "booked").sum()),
        errors=int((out.error != "").sum()),
        tool_calls_mean=round(out.tool_calls.mean(), 2), model_calls_mean=round(out.model_calls.mean(), 2),
        latency_ms_median=round(out.latency_ms.median(), 1), cost_usd_total=round(out.cost_usd.sum(), 5),
        cost_usd_per_chat=round(out.cost_usd.mean(), 6), replayed_from_cache=sp.client.usage.cache_hits,
    )
    return out, summary


def _main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Run one specialist on its share of a dataset split.")
    ap.add_argument("--agent", default="booking_status", choices=["booking_status", "warranty_recall", "billing_lease"])
    ap.add_argument("--split", default="validation", choices=["train", "validation", "test"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--effort", default=None)
    a = ap.parse_args()
    out, s = evaluate(a.agent, a.split, a.model, a.prompt, a.effort)
    res_dir = path("results_dir"); res_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{a.agent}_{s['model'].split('/')[-1]}_{s['prompt'].split('/')[-1].removesuffix('.md')}_{s['reasoning_effort']}_{a.split}"
    out.to_csv(res_dir / f"{tag}.csv", index=False)
    (res_dir / f"{tag}.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    print(json.dumps(s, indent=1))
    print("\nReplies:")
    for _, r in out.iterrows():
        flag = "  <-- unbacked promise" if r.unbacked_promises else ""
        print(f"\n[{r.id}] {r.request_type} | action={r.action} | tools={r.tools or '-'}{flag}\n  {r.reply[:300]}")
    print(f"\nSaved: {res_dir / tag}.csv and .json")


if __name__ == "__main__":
    _main()
