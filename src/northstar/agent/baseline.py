"""Single-agent baseline: one large model with every tool, no router, no fast path.

Why it exists: the brief asks us to show that the multi-agent design is worth it.
This runs the same validation chats through one Claude Sonnet 5.5 agent that has all
the tools and the same rules, and compares it with the full pipeline on the measures
that matter: chats that needed a person, false promises, cost and wait time.

Run:  python -m northstar.agent.baseline --split validation
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

import pandas as pd

from northstar.agent.router import turns_from_row
from northstar.agent.specialist import Specialist
from northstar.config import path
from northstar.contracts import AgentAction
from northstar.data import load_conversations
from northstar.dms.store import DealerSystem


def evaluate(split: str = "validation", agent: Optional[Specialist] = None) -> tuple[pd.DataFrame, dict]:
    sa = agent or Specialist("single_agent")
    df = load_conversations(split)
    rows = []
    for _, r in df.iterrows():
        res = sa.run(r["id"], turns_from_row(r), None, DealerSystem(), language_hint=r["language"])
        rep = res.reply
        unbacked = [c for c in rep.commitments if c.backed_by_tool is None]
        rows.append(dict(
            id=r["id"], gold_type=r["request_type"], difficulty=r["difficulty"],
            adversarial_type=r["adversarial_type"] if isinstance(r["adversarial_type"], str) else "",
            gold_escalation=bool(r["needs_escalation"]), action=rep.action.value,
            escalated=rep.action == AgentAction.ESCALATED,
            handoff_reason=rep.handoff.reason.value if rep.handoff else "",
            tools=",".join(rep.tools_used), tool_calls=res.tool_calls,
            unbacked_promises=";".join(f"{c.kind.value}: {c.detail}" for c in unbacked),
            reply=rep.text, latency_ms=res.latency_ms, cost_usd=res.cost_usd, error=res.error))
    out = pd.DataFrame(rows)
    g, e = out[out.gold_escalation], out[out.escalated]
    summary = dict(
        design="single_agent", model=sa.model, prompt=sa.prompt_name, reasoning_effort=sa.effort, split=split, n=len(out),
        handoff_recall=round(g.escalated.mean(), 3) if len(g) else None,
        handoff_precision=round(e.gold_escalation.mean(), 3) if len(e) else None,
        replies_with_unbacked_promise=int((out.unbacked_promises != "").sum()),
        bookings_made=int((out.action == "booked").sum()),
        errors=int((out.error != "").sum()),
        tool_calls_mean=round(out.tool_calls.mean(), 2),
        latency_ms_median=round(out.latency_ms.median(), 1),
        cost_usd_total=round(out.cost_usd.sum(), 5), cost_usd_per_chat=round(out.cost_usd.mean(), 6),
        replayed_from_cache=sa.client.usage.cache_hits,
    )
    return out, summary


def compare(single: dict, split: str) -> str:
    """Side by side with the last full-pipeline run, if there is one."""
    f = path("results_dir") / f"pipeline_{split}.json"
    if not f.exists():
        return "(Run python -m northstar.agent.pipeline first to see the comparison.)"
    multi = json.loads(f.read_text(encoding="utf-8"))
    keys = [("handoff_recall", "Needed a person and got one"), ("handoff_precision", "Sent to a person and needed it"),
            ("replies_with_unbacked_promise", "Replies with a false promise"), ("bookings_made", "Bookings made"),
            ("latency_ms_median", "Median wait (ms)"), ("cost_usd_per_chat", "Cost per chat (USD)")]
    lines = [f"{'':34}{'multi-agent':>14}{'single agent':>14}"]
    for k, label in keys:
        lines.append(f"{label:34}{str(multi.get(k)):>14}{str(single.get(k)):>14}")
    return "\n".join(lines)


def _main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Run the single-agent baseline on a split and compare with the pipeline.")
    ap.add_argument("--split", default="validation", choices=["train", "validation", "test"])
    a = ap.parse_args()
    out, s = evaluate(a.split)
    res_dir = path("results_dir"); res_dir.mkdir(parents=True, exist_ok=True)
    tag = f"single_agent_{a.split}"
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
        if r.unbacked_promises:
            flags.append("unbacked promise")
        flag = ("  <-- " + "; ".join(flags)) if flags else ""
        print(f"[{r.id}] {r.gold_type} | {r.action}{flag}")
    print("\nComparison with the full pipeline:\n" + compare(s, a.split))
    print(f"\nSaved: {res_dir / tag}.csv and .json")


if __name__ == "__main__":
    _main()
