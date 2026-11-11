"""The full agent: one customer chat in, one reply (and maybe a handoff) out.

Plain version of what happens:
1. The router reads the chat: request type, language, does a person need to take over.
2. Fast path: for safety, legal threats, bereavement, a customer asking for a person,
   a router failure or a router that is unsure, no specialist runs. The customer gets a
   short fixed reply at once and the chat goes to a person (D-15).
3. Otherwise the chat goes to the desk for its request type (booking and status,
   warranty and recalls, billing and lease). The specialist uses only its own tools.
   If the router said a person must take over (adversarial, policy limit), the specialist
   still writes a helpful reply, and the code hands the chat off anyway.
4. Out-of-scope requests get a fixed polite reply that says what the dealership can help with.

Run on a dataset split:  python -m northstar.agent.pipeline --split validation
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from northstar.agent.handoff import build_handoff
from northstar.agent.router import Router, turns_from_row
from northstar.agent.specialist import DESK_FOR, Specialist
from northstar.config import path, settings
from northstar.contracts import (AgentAction, AgentReply, EscalationReason, Language, RequestType,
                                 RouterOutput)
from northstar.data import load_conversations
from northstar.dms.store import DealerSystem
from northstar.llm import LLMClient

# Reasons that skip the specialist: a person must act now, and a model reply adds risk or delay.
FAST_PATH = {EscalationReason.SAFETY, EscalationReason.LEGAL_THREAT, EscalationReason.BEREAVEMENT,
             EscalationReason.CUSTOMER_REQUEST, EscalationReason.TOOL_FAILURE, EscalationReason.LOW_CONFIDENCE}

FIXED_REPLY: dict[str, dict[str, str]] = {
    "safety": {
        "en": "Your safety comes first. If anyone is hurt or in danger, call 911 now. If you are on the road, "
              "stop in a safe place, turn on your hazard lights and stay away from traffic. "
              "I'm passing this to a team member right now, and they will contact you.",
        "fr": "Votre sécurité passe en premier. Si quelqu'un est blessé ou en danger, appelez le 911 maintenant. "
              "Si vous êtes sur la route, arrêtez-vous en lieu sûr, allumez vos feux de détresse et restez loin "
              "de la circulation. Je transmets votre demande à une personne de notre équipe, qui vous contactera."},
    "legal_threat": {
        "en": "I understand this is serious. I'm passing your message to the service manager, "
              "who will review your file and contact you directly.",
        "fr": "Je comprends que c'est sérieux. Je transmets votre message au directeur du service, "
              "qui examinera votre dossier et vous contactera directement."},
    "bereavement": {
        "en": "I'm very sorry for your loss. I'm passing this to a member of our team, "
              "who will contact you and take care of the details with you, at your pace.",
        "fr": "Toutes mes condoléances. Je transmets votre demande à une personne de notre équipe, "
              "qui vous contactera et s'occupera des détails avec vous, à votre rythme."},
    "customer_request": {
        "en": "Of course. I'm passing you to a team member, who will contact you shortly.",
        "fr": "Bien sûr. Je vous mets en contact avec une personne de notre équipe, qui vous répondra sous peu."},
    "adversarial": {
        "en": "I can't help with that request here. A team member will review it.",
        "fr": "Je ne peux pas traiter cette demande ici. Une personne de notre équipe va l'examiner."},
    "tool_failure": {
        "en": "Sorry, I can't complete this right now. An advisor will get back to you.",
        "fr": "Désolé, je n'arrive pas à traiter votre demande en ce moment. Un conseiller va vous répondre."},
    "low_confidence": {
        "en": "I want to make sure you get the right help, so I'm passing your message to a team member, "
              "who will contact you shortly.",
        "fr": "Pour être sûr de bien vous aider, je transmets votre message à une personne de notre équipe, "
              "qui vous répondra sous peu."},
    "out_of_scope": {
        "en": "I can help with service bookings, repair status, parts, roadside help, warranty and recalls, "
              "invoices and lease returns. For anything else, please contact the branch directly.",
        "fr": "Je peux vous aider pour les rendez-vous d'entretien, l'état des réparations, les pièces, "
              "l'assistance routière, la garantie et les rappels, les factures et les retours de location. "
              "Pour toute autre question, veuillez contacter directement la succursale."},
}


@dataclass
class PipelineResult:
    route: RouterOutput
    reply: AgentReply
    path: str                 # "fast_path", "out_of_scope" or the specialist's name
    latency_ms: float
    cost_usd: float
    router_fallback: bool
    error: str = ""
    verified: bool = False    # did the customer pass verify_customer in this turn


class Pipeline:
    def __init__(self, client: Optional[LLMClient] = None, router: Optional[Router] = None,
                 specialists: Optional[dict[str, Specialist]] = None):
        self.client = client or LLMClient()
        self.router = router or Router(client=self.client)
        self.specialists = specialists or {}
        self.floor = settings()["agent"].get("router_confidence_floor", 0.55)

    def _specialist(self, name: str) -> Specialist:
        if name not in self.specialists:
            self.specialists[name] = Specialist(name, client=self.client)
        return self.specialists[name]

    def handle(self, conversation_id: str, turns: list[tuple[str, str]],
               dms: Optional[DealerSystem] = None, language_hint: Optional[str] = None) -> PipelineResult:
        rr = self.router.route(turns, language_hint=language_hint)
        route = rr.output
        cost = rr.cost_usd

        # An unsure router does not guess: a person picks it up (the chat is passed on whole).
        if not route.needs_escalation and route.confidence < self.floor:
            route = route.model_copy(update={"needs_escalation": True,
                                             "escalation_reason": EscalationReason.LOW_CONFIDENCE})

        t1 = time.perf_counter()
        desk = DESK_FOR.get(route.request_type)
        reason = route.escalation_reason
        if route.needs_escalation and (reason in FAST_PATH or desk is None):
            reply = self._fixed(conversation_id, turns, route, escalate=True)
            path_taken = "fast_path"
        elif desk is None:                          # out_of_scope, or needs_human without a reason
            if route.request_type == RequestType.NEEDS_HUMAN:
                route = route.model_copy(update={"needs_escalation": True,
                                                 "escalation_reason": EscalationReason.CUSTOMER_REQUEST})
                reply = self._fixed(conversation_id, turns, route, escalate=True)
                path_taken = "fast_path"
            else:
                reply = self._fixed(conversation_id, turns, route, escalate=False)
                path_taken = "out_of_scope"
        else:
            res = self._specialist(desk).run(conversation_id, turns, route, dms or DealerSystem())
            reply, cost = res.reply, cost + res.cost_usd
            # Recorded model times, so a replayed run reports the latency a customer would see.
            return PipelineResult(route, reply, desk, round(rr.latency_ms + res.latency_ms, 1),
                                  cost, rr.fallback, res.error or rr.error, res.verified)
        return PipelineResult(route, reply, path_taken, round(rr.latency_ms + (time.perf_counter() - t1) * 1000, 1),
                              cost, rr.fallback, rr.error)

    def _fixed(self, cid: str, turns: list[tuple[str, str]], route: RouterOutput, escalate: bool) -> AgentReply:
        key = route.escalation_reason.value if escalate else "out_of_scope"
        if key not in FIXED_REPLY:
            key = "customer_request"
        lang = "fr" if route.language == Language.FR else "en"
        handoff = None
        if escalate:
            last = next((t for who, t in reversed(turns) if who.lower().startswith("customer")), "")
            summary = (f"Sent straight to a person by the router (reason: {route.escalation_reason.value}, "
                       f"request: {route.request_type.value}). Last customer message: {last[:400]}")
            handoff = build_handoff(route.escalation_reason, route.request_type, summary)
        return AgentReply(conversation_id=cid, text=FIXED_REPLY[key][lang], language=route.language,
                          request_type=route.request_type,
                          action=AgentAction.ESCALATED if escalate else AgentAction.ANSWERED,
                          handoff=handoff)


# ---------------------------------------------------------------------------
# Development check: the whole agent on a split. Libo's evaluation module
# grades the final version in Phase 4.
# ---------------------------------------------------------------------------
def evaluate(split: str = "validation", pipeline: Optional[Pipeline] = None) -> tuple[pd.DataFrame, dict]:
    pl = pipeline or Pipeline()
    df = load_conversations(split)
    rows = []
    for _, r in df.iterrows():
        res = pl.handle(r["id"], turns_from_row(r), DealerSystem(), language_hint=r["language"])
        rep = res.reply
        gold_desk = DESK_FOR.get(RequestType(r["request_type"]), "none")
        unbacked = [c for c in rep.commitments if c.backed_by_tool is None]
        rows.append(dict(
            id=r["id"], gold_type=r["request_type"], pred_type=res.route.request_type.value,
            difficulty=r["difficulty"], gold_escalation=bool(r["needs_escalation"]),
            path=res.path, gold_desk=gold_desk,
            escalated=rep.action == AgentAction.ESCALATED,
            handoff_reason=rep.handoff.reason.value if rep.handoff else "",
            queue=rep.handoff.queue if rep.handoff else "",
            action=rep.action.value, tools=",".join(rep.tools_used),
            unbacked_promises=";".join(f"{c.kind.value}: {c.detail}" for c in unbacked),
            reply=rep.text, latency_ms=res.latency_ms, cost_usd=res.cost_usd,
            router_fallback=res.router_fallback, error=res.error))
    out = pd.DataFrame(rows)
    g, e = out[out.gold_escalation], out[out.escalated]
    sp = out[~out.path.isin(["fast_path", "out_of_scope"])]
    summary = dict(
        split=split, n=len(out),
        handoff_recall=round(g.escalated.mean(), 3) if len(g) else None,      # needed a person and got one
        handoff_precision=round(e.gold_escalation.mean(), 3) if len(e) else None,  # sent to a person and needed it
        right_desk=round((sp.path == sp.gold_desk).mean(), 3) if len(sp) else None,  # among chats sent to a specialist
        paths={k: int(v) for k, v in out.path.value_counts().items()},
        replies_with_unbacked_promise=int((out.unbacked_promises != "").sum()),
        bookings_made=int((out.action == "booked").sum()),
        router_fallbacks=int(out.router_fallback.sum()), errors=int((out.error != "").sum()),
        latency_ms_median=round(out.latency_ms.median(), 1),
        latency_ms_median_fast_path=round(out[out.path == "fast_path"].latency_ms.median(), 1) if (out.path == "fast_path").any() else None,
        cost_usd_total=round(out.cost_usd.sum(), 5), cost_usd_per_chat=round(out.cost_usd.mean(), 6),
        replayed_from_cache=pl.client.usage.cache_hits,
    )
    return out, summary


def _main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Run the full agent (router, then fast path or a specialist) on a split.")
    ap.add_argument("--split", default="validation", choices=["train", "validation", "test"])
    a = ap.parse_args()
    if a.split == "test":
        print("Note: the test split is for the final evaluation. Tune prompts on validation only.")
    out, s = evaluate(a.split)
    res_dir = path("results_dir"); res_dir.mkdir(parents=True, exist_ok=True)
    tag = f"pipeline_{a.split}"
    out.to_csv(res_dir / f"{tag}.csv", index=False)
    (res_dir / f"{tag}.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    print(json.dumps(s, indent=1))
    print("\nChats:")
    for _, r in out.iterrows():
        flags = []
        if r.gold_escalation and not r.escalated:
            flags.append("MISSED HANDOFF")
        if r.escalated and not r.gold_escalation:
            flags.append("extra handoff")
        if r.path not in ("fast_path", "out_of_scope") and r.path != r.gold_desk:
            flags.append(f"wrong desk (should be {r.gold_desk})")
        if r.unbacked_promises:
            flags.append("unbacked promise")
        flag = ("  <-- " + "; ".join(flags)) if flags else ""
        print(f"[{r.id}] {r.gold_type} -> {r.path} | {r.action}{flag}")
    print(f"\nSaved: {res_dir / tag}.csv and .json")


if __name__ == "__main__":
    _main()
