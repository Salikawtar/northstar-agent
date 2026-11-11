"""Hand-written test chats (task 19): run the full agent on data/handwritten/chats.yaml
and check each chat against its expected result.

Unlike the dataset runs, which measure averages, each chat here tests ONE situation and
passes or fails. Once recorded, the run replays for free, so it can be repeated after
every change (Jessica's checks, Neeraj's router) to see whether something broke.

Run:  python -m northstar.agent.scenarios
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yaml

from northstar.agent.pipeline import Pipeline, PipelineResult
from northstar.config import ROOT, path
from northstar.contracts import AgentAction
from northstar.dms.store import DealerSystem

CHATS = ROOT / "data" / "handwritten" / "chats.yaml"
PATHS = {"fast_path", "out_of_scope", "booking_status", "warranty_recall", "billing_lease"}
KEYS = {"path", "escalated", "reason", "queue", "urgency", "action", "verified",
        "tools_include", "tools_exclude", "must_not_match"}


def load_chats(file: Path = CHATS) -> list[dict[str, Any]]:
    chats = yaml.safe_load(file.read_text(encoding="utf-8"))
    for c in chats:
        unknown = set(c["expect"]) - KEYS
        if unknown:
            raise ValueError(f"{c['id']}: unknown expectation {sorted(unknown)}")
    return chats


def _as_list(x) -> list:
    return x if isinstance(x, list) else [x]


def check(chat: dict[str, Any], res: PipelineResult) -> list[str]:
    """Return the list of failed checks (empty list = pass)."""
    e, rep = chat["expect"], res.reply
    h = rep.handoff
    fails = []
    if "path" in e and res.path not in _as_list(e["path"]):
        fails.append(f"went to {res.path}, expected {e['path']}")
    escalated = rep.action == AgentAction.ESCALATED
    if "escalated" in e and escalated not in _as_list(e["escalated"]):
        fails.append("handed off" if escalated else "did not hand off")
    for k in ("reason", "queue", "urgency"):
        if k in e:
            got = (h.reason.value if k == "reason" else h.queue if k == "queue" else h.urgency.value) if h else None
            if got != e[k]:
                fails.append(f"{k} {got}, expected {e[k]}")
    if "action" in e and rep.action.value not in _as_list(e["action"]):
        fails.append(f"action {rep.action.value}, expected {e['action']}")
    if "verified" in e and res.verified != e["verified"]:
        fails.append("customer verified" if res.verified else "customer not verified")
    used = set(rep.tools_used)
    missing = [t for t in e.get("tools_include", []) if t not in used]
    if missing:
        fails.append(f"did not use {', '.join(missing)}")
    banned = [t for t in e.get("tools_exclude", []) if t in used]
    if banned:
        fails.append(f"used {', '.join(banned)}")
    for pat in e.get("must_not_match", []):
        m = re.search(pat, rep.text, re.I)
        if m:
            fails.append(f'reply says "{m.group(0)}"')
    unbacked = [c for c in rep.commitments if c.backed_by_tool is None]
    if unbacked:
        fails.append("unbacked promise: " + "; ".join(f"{c.kind.value} ({c.detail})" for c in unbacked))
    if re.search(r"\bP-\d{2}\b", rep.text):
        fails.append("shows a rule id")
    if res.error:
        fails.append(f"error: {res.error}")
    return fails


def run(pipeline: Optional[Pipeline] = None, file: Path = CHATS) -> tuple[pd.DataFrame, dict]:
    pl = pipeline or Pipeline()
    rows = []
    for chat in load_chats(file):
        turns = [(who, text) for who, text in chat["turns"]]
        res = pl.handle(chat["id"], turns, DealerSystem(), language_hint=chat.get("language"))
        fails = check(chat, res)
        rows.append(dict(id=chat["id"], title=chat["title"], passed=not fails, failed_checks=" | ".join(fails),
                         path=res.path, action=res.reply.action.value,
                         handoff=f"{res.reply.handoff.reason.value} -> {res.reply.handoff.queue}" if res.reply.handoff else "",
                         tools=",".join(res.reply.tools_used), reply=res.reply.text,
                         latency_ms=res.latency_ms, cost_usd=res.cost_usd))
    out = pd.DataFrame(rows)
    summary = dict(n=len(out), passed=int(out.passed.sum()), failed=int((~out.passed).sum()),
                   cost_usd_total=round(out.cost_usd.sum(), 5), replayed_from_cache=pl.client.usage.cache_hits)
    return out, summary


def _main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    argparse.ArgumentParser(description="Run the hand-written test chats through the full agent.").parse_args()
    out, s = run()
    res_dir = path("results_dir"); res_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(res_dir / "handwritten.csv", index=False)
    (res_dir / "handwritten.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    print(json.dumps(s, indent=1) + "\n")
    for _, r in out.iterrows():
        mark = "PASS" if r.passed else "FAIL"
        print(f"{mark}  {r.id}  {r.title}  ({r.path}, {r.action}{', ' + r.handoff if r.handoff else ''})")
        if not r.passed:
            print(f"      why: {r.failed_checks}")
            print(f"      reply: {r.reply[:300]}")
    print(f"\nSaved: {res_dir / 'handwritten'}.csv and .json")


if __name__ == "__main__":
    _main()
