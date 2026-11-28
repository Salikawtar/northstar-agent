"""The router options, built from saved answers only (no training, no API calls).

Option 1  : tuned model alone. 1a = her rule (reason guessed from the type); 1 = with the attack answer.
Option 2  : two-step. The tuned model answers type, escalation and language for every chat; a language model
            (Jev or Haiku) gives the reason only for the chats the tuned model sends to a person.
Option 2c : two-step plus cascade. Also, when the tuned model is unsure (below the team's 0.55 floor), the
            language model's whole answer is used instead of handing the chat to a person.
Option 3  : a language model alone (Jev, Haiku or Sonnet), as the team's agent uses Haiku today.

Every option ends in the same table of answers (type, escalate, reason, confidence) plus which chats called a
language model and what that cost, so all options are scored by the same code (routing.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from northstar.finetune.study import baselines as B
from northstar.finetune.study import cv_analysis as A
from northstar.finetune.study import protocol as P
from northstar.finetune.study import routing as R
from northstar.finetune.study.metrics import escalation_scores

PROB_GRID = np.round(np.arange(0.05, 0.951, 0.05), 2)       # cut-offs tried, as probabilities


def _logit(p: float) -> float:
    return float(np.log(p / (1 - p)))


def choose_cutoff(oof: dict, pool: pd.DataFrame, epoch: int, head: str = "escalation", label: str = "escalation_label"):
    """Cut-off for a yes/no answer chosen on the pool's out-of-fold scores by the highest mean F2 over seeds
    (the protocol's rule). Ties go to the higher cut-off (fewer false alarms). Returns (logit cut-off, table)."""
    y = pool[label].values
    rows = []
    for p in PROB_GRID:
        f2 = [escalation_scores(y, arr[head][epoch - 1], _logit(p))["f2"] for arr in oof.values()]
        rows.append(dict(cutoff_probability=p, f2_mean=float(np.mean(f2)), f2_sd=float(np.std(f2, ddof=1))))
    table = pd.DataFrame(rows)
    best = table.loc[table["f2_mean"] == table["f2_mean"].max(), "cutoff_probability"].max()
    return _logit(float(best)), table


def tuned_answers(oof: dict, pool: pd.DataFrame, epoch: int, esc_cut: float = 0.0, attack_cut: float | None = None) -> pd.DataFrame:
    """The tuned model's combined answer (average of the seeds) at one epoch and cut-off."""
    s = A.summary_at_epoch(oof, pool, epoch)
    logits = s["ensemble_type_logits"]
    out = pd.DataFrame({"id": pool["id"].values,
                        "type": [P.REQUEST_TYPES[i] for i in logits.argmax(-1)],
                        "esc": s["ensemble_escalation_logits"] > esc_cut,
                        "confidence": R.softmax_confidence(logits)})
    if attack_cut is not None and "ensemble_attack_logits" in s:
        out["attack"] = s["ensemble_attack_logits"] > attack_cut
    return out


def combine_llm(repeats: list) -> pd.DataFrame:
    """One answer per chat from a language model's repeats: type and escalation by B.vote (averages), the
    reason by majority (ties go to the first repeat); cost and latency are averages over repeats."""
    v = B.vote(repeats)
    reasons = pd.concat([r["reason"].rename(i) for i, r in enumerate(repeats)], axis=1)
    def mode(row):
        counts = row.value_counts()
        top = counts[counts == counts.max()].index
        return row.iloc[0] if row.iloc[0] in top else top[0]
    return pd.DataFrame({"id": repeats[0]["id"].values,
                         "type": [P.REQUEST_TYPES[i] for i in v["type_probs"].argmax(-1)],
                         "esc": v["esc_score"] > 0,
                         "reason": reasons.apply(mode, axis=1).values,
                         "confidence": np.mean([r["confidence"].fillna(1.0).values for r in repeats], axis=0),
                         "cost_usd": np.mean([r["cost_usd"].values for r in repeats], axis=0),
                         "latency_ms": np.mean([r["latency_ms"].values for r in repeats], axis=0)})


def _result(types, esc, reasons, conf, called, llm_cost) -> pd.DataFrame:
    return pd.DataFrame({"type": list(types), "esc": np.asarray(esc, bool), "reason": list(reasons),
                         "confidence": np.asarray(conf, float), "called_llm": np.asarray(called, bool),
                         "llm_cost": np.where(np.asarray(called, bool), llm_cost, 0.0)})


def option_her_rule(t: pd.DataFrame) -> pd.DataFrame:
    reasons = [R.reason_from_type(ty) if e else "none" for ty, e in zip(t["type"], t["esc"])]
    return _result(t["type"], t["esc"], reasons, t["confidence"], np.zeros(len(t), bool), 0.0)


def option_attack_head(t: pd.DataFrame) -> pd.DataFrame:
    esc = t["esc"].values | t["attack"].values                # an attack always goes to a person
    reasons = [R.reason_from_type(ty, a) if e else "none" for ty, e, a in zip(t["type"], esc, t["attack"])]
    return _result(t["type"], esc, reasons, t["confidence"], np.zeros(len(t), bool), 0.0)


def option_two_step(t: pd.DataFrame, llm: pd.DataFrame) -> pd.DataFrame:
    called = t["esc"].values
    reasons = [(lr if lr != "none" else R.reason_from_type(ty)) if c else "none"
               for ty, c, lr in zip(t["type"], called, llm["reason"])]
    return _result(t["type"], t["esc"], reasons, t["confidence"], called, llm["cost_usd"].values)


def option_cascade(t: pd.DataFrame, llm: pd.DataFrame, floor: float = R.FLOOR) -> pd.DataFrame:
    unsure = (~t["esc"].values) & (t["confidence"].values < floor)
    two = option_two_step(t, llm)
    types = np.where(unsure, llm["type"].values, two["type"].values)
    esc = np.where(unsure, llm["esc"].values, two["esc"].values)
    reasons = np.where(unsure, llm["reason"].values, two["reason"].values)
    conf = np.where(unsure, llm["confidence"].values, two["confidence"].values)
    called = two["called_llm"].values | unsure
    return _result(types, esc, reasons, conf, called, llm["cost_usd"].values)


def option_llm_alone(llm: pd.DataFrame) -> pd.DataFrame:
    reasons = [r if e else "none" for r, e in zip(llm["reason"], llm["esc"])]
    return _result(llm["type"], llm["esc"], reasons, llm["confidence"], np.ones(len(llm), bool), llm["cost_usd"].values)


def score(pool: pd.DataFrame, ans: pd.DataFrame, floor: float = R.FLOOR) -> tuple:
    """(scores, per-chat routing) for one option, with the team's pipeline and grader rules."""
    routed = R.route_all(pool, ans["type"], ans["esc"], ans["reason"], ans["confidence"], floor)
    s = R.handoff_scores(routed)
    s.update(type_accuracy=float((ans["type"].values == pool["request_type"].values).mean()),
             llm_share=float(ans["called_llm"].mean()), usd_per_1000=float(ans["llm_cost"].sum() / len(ans) * 1000))
    return s, routed


FLOOR_GRID = (0.55, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.0)


def choose_floor(pool: pd.DataFrame, ans: pd.DataFrame, grid=FLOOR_GRID):
    """The "unsure" line for a tuned model (the team's pipeline sends a chat to a person when the router is less
    sure than this of the request type; 0.55 was set for Haiku). Rule, fixed before the final run: the line with
    the highest strict handled-right on the pool, but never one that misses more handoffs than the team's 0.55
    (safety first). Ties go to the higher line. Returns (line, table)."""
    rows = []
    for f in grid:
        s, _ = score(pool, ans, f)
        rows.append(dict(unsure_line=f, handled_right=s["handled_right"], missed=s["missed"], extra_handoffs=s["extra_handoffs"],
                         kept_wrong_desk=s["kept_wrong_desk"], right_team=s["right_team"]))
    table = pd.DataFrame(rows)
    allowed = table[table["missed"] <= int(table.loc[table["unsure_line"] == R.FLOOR, "missed"].iloc[0])]
    best = allowed[allowed["handled_right"] == allowed["handled_right"].max()]["unsure_line"].max()
    return float(best), table
