"""Measure the input check without any model call (free).

- On the 200 dataset chats: how many attack chats it flags, and how many normal chats it
  flags by mistake (false alarms).
- On the 75 red-team attacks (held out: the rules were not tuned on them): how many it
  flags, by attack type. Only prompt injection is meant to be caught here; the other
  attack types are for the router, the specialist rules and the output check.

The output check is measured inside the full pipeline runs (replies_blocked_by_output_check),
because it needs what the tools returned.

Run:  python -m northstar.guardrails.evaluate
"""
from __future__ import annotations

import json
import sys

from northstar.agent.router import turns_from_row
from northstar.data import load_conversations, load_redteam
from northstar.guardrails.input_check import check_input


def evaluate() -> dict:
    d = load_conversations()
    attack = d.adversarial_type.fillna("") != ""
    flagged = d.apply(lambda r: check_input(turns_from_row(r)).injection, axis=1)
    inj = d.adversarial_type == "prompt_injection"
    rt = load_redteam()
    rt_flag = rt.attack_message.map(lambda m: check_input([("customer", m)]).injection)
    by_type = {t: f"{int(rt_flag[rt.attack_type == t].sum())} of {int((rt.attack_type == t).sum())}"
               for t in sorted(rt.attack_type.unique())}
    return dict(
        dataset_prompt_injections_flagged=f"{int(flagged[inj].sum())} of {int(inj.sum())}",
        dataset_other_attacks_flagged=f"{int(flagged[attack & ~inj].sum())} of {int((attack & ~inj).sum())}",
        dataset_normal_chats_flagged_by_mistake=f"{int(flagged[~attack].sum())} of {int((~attack).sum())}",
        redteam_flagged_by_attack_type=by_type,
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(evaluate(), indent=1, ensure_ascii=False))
