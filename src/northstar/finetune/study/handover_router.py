"""The study's final fine-tuned router as a live model (LoRA + attack head), usable inside the team's pipeline.

    python -m northstar.finetune.study.handover_router "stuck on the 401, car won't start"   # try one message

    router = TunedRouter()                                             # weights: study/results/step06/fine_tuned/balanced
    out = router.predict("stuck on the 401, car won't start")          # plain dict
    res = router.route(turns)                                          # the team's RouteResult

The evaluation replays this router's recorded decisions (setup full_agent_router_finetuned_lora); set
NORTHSTAR_LIVE_FINETUNED=1 to run the model itself instead. First use downloads xlm-roberta-base (about 1 GB).

What it does, exactly as in the final run (config/final_settings.json, setup "balanced"):
  * reads the customer's first message;
  * XLM-RoBERTa base with the trained LoRA add-ons and three answers: request type, needs a person, attack;
  * averages the five trained seeds' scores (or uses fewer seeds for speed; `seeds=`);
  * a person is needed when the needs-a-person score passes 0.10, or the attack score passes 0.05;
  * reason: attack -> adversarial; otherwise from the request type (roadside -> safety, contested bill -> policy limit...);
  * language from the word rule;
  * confidence rescaled so that the team's 0.55 unsure line hands over exactly the chats below the router's own 0.40 line.

Memory: the frozen base model is loaded once; only the small trained parts of each seed (a few MB) are swapped in,
so five seeds cost five passes of time, not five models of memory. Needs torch, transformers and peft.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from northstar.finetune.study import protocol as P
from northstar.finetune.study import routing as R
from northstar.finetune.study.final_run import SETTINGS_PATH, report_confidence


WEIGHTS_DIR = P.STUDY / "results" / "step06" / "fine_tuned" / "balanced"     # five seeds, 1.2 MB each


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


class TunedRouter:
    def __init__(self, weights_dir=WEIGHTS_DIR, setup: str = "balanced", seeds=None, device: str = "cpu", threads: int | None = 2):
        import torch
        from transformers import AutoTokenizer

        from northstar.finetune.study.model import HEAD_SIZES, RouterModel

        s = json.loads(Path(SETTINGS_PATH).read_text(encoding="utf-8"))["fine_tuned"][setup]
        t = s["training"]
        if not t.get("lora"):
            raise ValueError("TunedRouter loads LoRA setups (small trained parts); the full fine-tuning weights were not kept")
        self.setup, self.settings = setup, s
        self.esc_cut, self.attack_cut, self.own_line = s["escalation_cutoff"], s["attack_cutoff"], s["unsure_line"]
        self.max_length = t["max_length"]
        self.device = torch.device(device)
        if threads and self.device.type == "cpu":
            torch.set_num_threads(threads)
        files = sorted(Path(weights_dir).glob("seed*_trained_weights.pt"))
        if seeds is not None:
            files = [f for f in files if int(f.name[4:].split("_")[0]) in set(seeds)]
        if not files:
            raise FileNotFoundError(f"no seed*_trained_weights.pt in {weights_dir}")
        self.tokenizer = AutoTokenizer.from_pretrained("xlm-roberta-base")
        lora = dict(r=t["lora_r"], lora_alpha=t["lora_alpha"], lora_dropout=t["lora_dropout"], bias="none",
                    target_modules=["query", "value"])
        self.model = RouterModel("xlm-roberta-base", {h: HEAD_SIZES[h] for h in t["heads"]}, t["dropout"], None, lora)
        self.model.to(self.device).eval()
        self.seed_parts = [torch.load(f, map_location=self.device) for f in files]
        self.seeds = [int(f.name[4:].split("_")[0]) for f in files]
        self._torch = torch
        self.model_name, self.prompt_name, self.effort = "finetuned-xlm-roberta-base-lora-attack", "none", "none"

    def scores(self, text: str) -> dict:
        """Average of the seeds' raw scores for one chat."""
        torch = self._torch
        enc = self.tokenizer(text, truncation=True, max_length=self.max_length, return_tensors="pt").to(self.device)
        acc = None
        with torch.no_grad():
            for part in self.seed_parts:
                self.model.load_state_dict(part, strict=False)      # swap in this seed's add-ons and heads
                out = self.model(enc["input_ids"], enc["attention_mask"])
                vals = {k: v.float().cpu().numpy()[0] for k, v in out.items()}
                acc = vals if acc is None else {k: acc[k] + vals[k] for k in acc}
        return {k: v / len(self.seed_parts) for k, v in acc.items()}

    def predict(self, first_message: str) -> dict:
        t0 = time.perf_counter()
        s = self.scores(first_message)
        z = s["type"] - s["type"].max()
        probs = np.exp(z) / np.exp(z).sum()
        rtype = P.REQUEST_TYPES[int(probs.argmax())]
        attack = bool(_sigmoid(s["attack"]) > self.attack_cut)
        escalate = bool(_sigmoid(s["escalation"]) > self.esc_cut) or attack
        reason = R.reason_from_type(rtype, attack) if escalate else "none"
        return dict(request_type=rtype, needs_escalation=escalate, escalation_reason=reason,
                    confidence=float(report_confidence([probs.max()], self.own_line)[0]),
                    raw_confidence=float(probs.max()), attack=attack, language=R.language_rule(first_message),
                    latency_ms=round((time.perf_counter() - t0) * 1000, 1))

    def route(self, turns, language_hint=None):
        """The team pipeline's router call. Inside the team repo it returns the team's RouteResult; elsewhere a dict."""
        first = next((text for who, text in turns if str(who).lower().startswith("customer")), "")
        p = self.predict(first)
        try:
            from northstar.agent.router import RouteResult
            from northstar.contracts import EscalationReason, Language, RequestType, RouterOutput
        except ImportError:
            return p
        out = RouterOutput(request_type=RequestType(p["request_type"]), needs_escalation=p["needs_escalation"],
                           escalation_reason=EscalationReason(p["escalation_reason"]), confidence=round(p["confidence"], 4),
                           language=Language(p["language"]))
        return RouteResult(out, p["latency_ms"], 0.0, len(self.tokenizer(first)["input_ids"]), 0)


if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) or "My car won't start and I'm stuck on the highway near exit 40."
    print(json.dumps(TunedRouter().predict(text), indent=1))
