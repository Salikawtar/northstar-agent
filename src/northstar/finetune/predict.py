"""The fine-tuned router behind the same plug as the prompted router.

`FinetunedRouter.route(turns)` returns the same `RouteResult` (with a `RouterOutput`)
as `northstar.agent.router.Router.route`, so the pipeline and the router evaluation
can use either one without any other change:

    python -m northstar.agent.router --split test --model finetuned

What each `RouterOutput` field comes from:
- request_type, needs_escalation, language: the three trained heads.
- confidence: the model's probability for the chosen request type (0 to 1), so the
  pipeline's confidence floor (settings: agent.router_confidence_floor) works as usual.
- escalation_reason: not learned (the dataset has no reason labels). A fixed rule picks
  the reason that sends the chat to the right queue (see REASON_FOR below). Known limitation.
- secondary_types: always empty (the model picks one type). Known limitation; not scored.

Runs on CPU by default: the router must not need a GPU in production, and CPU timing is
the honest latency to compare with the API routers.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import torch
from transformers import AutoTokenizer

from northstar.agent.router import RouteResult, format_conversation
from northstar.config import settings
from northstar.contracts import EscalationReason, Language, RequestType, RouterOutput
from northstar.finetune.model import LANGUAGES, REQUEST_TYPES, load_checkpoint

# Reason used when the model says "escalate". Chosen so build_handoff sends the chat to the
# right queue: safety goes to roadside, policy limits on money and warranty go to the service
# manager or warranty desk, everything else to the general queue.
REASON_FOR = {
    RequestType.NEEDS_HUMAN: EscalationReason.CUSTOMER_REQUEST,
    RequestType.ROADSIDE_ASSISTANCE: EscalationReason.SAFETY,
    RequestType.BILLING_DISPUTE: EscalationReason.POLICY_LIMIT,
    RequestType.WARRANTY_CLAIM: EscalationReason.POLICY_LIMIT,
    RequestType.RECALL_INQUIRY: EscalationReason.POLICY_LIMIT,
    RequestType.LEASE_END_RETURN: EscalationReason.POLICY_LIMIT,
}


def default_checkpoint() -> Path:
    return Path(settings()["models"].get("finetuned_router") or "models/finetuned_router")


class _NoUsage:
    cache_hits = 0       # no model calls, so nothing is replayed from the recordings


class _NoClient:
    usage = _NoUsage()


class FinetunedRouter:
    def __init__(self, checkpoint: Optional[Path] = None, device: str = "cpu"):
        folder = Path(checkpoint or default_checkpoint())
        if not (folder / "weights.pt").exists():
            raise FileNotFoundError(
                f"No fine-tuned router at {folder}. Train it first (python -m northstar.finetune.train_router "
                "select, then final), or point --checkpoint at the folder.")
        self.device = torch.device(device)
        self.net, self.cfg = load_checkpoint(folder, self.device)
        self.tok = AutoTokenizer.from_pretrained(self.cfg["base_model"])
        self.threshold = float(self.cfg.get("threshold", 0.5))
        self.max_length = int(self.cfg.get("max_length", 320))
        # Same attributes the evaluation summary reads from the prompted Router.
        self.model = f"finetuned-{self.cfg['base_model'].split('/')[-1]}"   # results file: router_finetuned-..._test
        self.prompt_name = "none"
        self.effort = "none"
        self.client = _NoClient()
        self.route([("customer", "warm-up")])     # first call loads kernels; keep it out of the timings

    @torch.inference_mode()
    def route(self, turns: list[tuple[str, str]], language_hint: Optional[str] = None) -> RouteResult:
        t0 = time.perf_counter()
        enc = self.tok(format_conversation(turns), truncation=True, max_length=self.max_length, return_tensors="pt")
        t, e, l = self.net(enc["input_ids"].to(self.device), enc["attention_mask"].to(self.device))
        p_type = torch.softmax(t.float(), -1)[0]
        conf, idx = float(p_type.max()), int(p_type.argmax())
        rtype = RequestType(REQUEST_TYPES[idx])
        escalate = float(torch.sigmoid(e.float())[0]) >= self.threshold
        lang = Language(LANGUAGES[int(l.argmax(-1)[0])])
        reason = REASON_FOR.get(rtype, EscalationReason.CUSTOMER_REQUEST) if escalate else EscalationReason.NONE
        out = RouterOutput(request_type=rtype, needs_escalation=escalate, escalation_reason=reason,
                           confidence=round(conf, 4), language=lang)
        return RouteResult(out, round((time.perf_counter() - t0) * 1000, 1), 0.0, int(enc["input_ids"].shape[1]), 0)
