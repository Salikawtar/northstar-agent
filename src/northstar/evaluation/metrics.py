"""Metrics: from per-chat grades to the numbers in the report, with honest ranges.

Main idea: one chat counts as a success only if every part of the rubric holds
(docs/evaluation_rubric.md). The other rates break success down so a reader can see
where a setup loses, and each one is tied to a business outcome:

| Metric                     | Business meaning                                                  |
|----------------------------|-------------------------------------------------------------------|
| task success               | chats handled correctly end to end (quality the customer gets)    |
| escalation recall          | chats that needed a person and got one (missed emergencies, legal)|
| escalation precision       | handoffs that were needed (advisor time spent on the right chats) |
| wrong commitments          | promises only a person may make (liability, the Air Canada case)  |
| invented facts             | wrong information given to a customer                             |
| policy failures            | any operating-policy rule broken                                  |
| handled without a person   | containment: the share of chats that saves advisor time           |
| cost per successful chat   | what one correct chat costs (Abhi's cost model)                   |

40 chats is a small test set: one chat moves a rate by 2.5 points. Every rate therefore
comes with a 95% Wilson interval, and setups are compared on the SAME chats with an exact
McNemar test (only the chats where the two setups disagree carry information).
"""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
import pandas as pd

Z = 1.959964   # 95%


def wilson(k: int, n: int) -> tuple[Optional[float], Optional[float]]:
    """95% Wilson interval for k successes out of n. Works at 0 and n, unlike the plain +-1.96 SE."""
    if n == 0:
        return None, None
    p = k / n
    d = 1 + Z ** 2 / n
    c = (p + Z ** 2 / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z ** 2 / (4 * n ** 2)) / d
    return round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)


def mcnemar_exact(a: pd.Series, b: pd.Series) -> dict[str, Any]:
    """Paired comparison of two setups on the same chats. b_only = chats only setup b got right."""
    a, b = a.astype(bool), b.astype(bool)
    a_only, b_only = int((a & ~b).sum()), int((~a & b).sum())
    n = a_only + b_only
    if n == 0:
        return dict(a_only=0, b_only=0, p_value=1.0)
    k = min(a_only, b_only)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return dict(a_only=a_only, b_only=b_only, p_value=round(min(1.0, 2 * p), 4))


def bootstrap_median(x: pd.Series, reps: int = 2000, seed: int = 894) -> tuple[Optional[float], Optional[float]]:
    x = x.dropna().to_numpy()
    if len(x) == 0:
        return None, None
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(x, size=(reps, len(x)), replace=True), axis=1)
    return round(float(np.percentile(meds, 2.5)), 1), round(float(np.percentile(meds, 97.5)), 1)


def combine(rule: dict[str, Any], llm: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Final grade of one chat. Rules decide what they can; the model grader the rest.
    No model grade (grader error or crash) counts against the chat, so a broken grader
    can never make a setup look better."""
    llm = llm or {}
    resolved = bool(llm.get("resolved_correctly", False))
    policy_ok_llm = bool(llm.get("policy_followed", False))
    invented = bool(llm.get("invented_facts", True)) if llm else True
    commit_llm = bool(llm.get("wrong_commitment", True)) if llm else True
    wrong_commitment = bool(rule["unbacked_promises"]) or commit_llm
    policy_failure = (not policy_ok_llm or wrong_commitment or rule["missed_handoff"]
                      or bool(rule["other_person_data"]) or bool(rule["own_data_unverified"])
                      or bool(rule["time_or_person_claims"]) or rule["queue_ok"] is False)
    success = (not rule["crashed"] and rule["rule_pass"] and resolved and policy_ok_llm
               and not invented and not wrong_commitment)
    return dict(success=success, resolved=resolved, policy_failure=policy_failure, invented=invented,
                wrong_commitment=wrong_commitment, graded=bool(llm))


def _rate(mask: pd.Series) -> dict[str, Any]:
    k, n = int(mask.sum()), int(len(mask))
    lo, hi = wilson(k, n)
    return dict(k=k, n=n, rate=round(k / n, 3) if n else None, ci_low=lo, ci_high=hi)


def summarize(df: pd.DataFrame) -> dict[str, Any]:
    """One setup's per-chat table -> its headline numbers."""
    esc_needed, esc_made = df[df.gold_escalation], df[df.escalated]
    routed = df[df.type_correct.notna()]
    ok = df[df.success]
    s = dict(
        n=len(df),
        task_success=_rate(df.success),
        request_type_accuracy=_rate(routed.type_correct.astype(bool)) if len(routed) else None,
        escalation_recall=_rate(esc_needed.escalated),
        escalation_precision=_rate(esc_made.gold_escalation) if len(esc_made) else None,
        missed_handoffs=int(df.missed_handoff.sum()),
        extra_handoffs=int(df.extra_handoff.sum()),
        wrong_commitments=_rate(df.wrong_commitment),
        invented_facts=_rate(df.invented),
        policy_failures=_rate(df.policy_failure),
        resolved_by_grader=_rate(df.resolved),
        tone_ok=_rate(df.grader_tone_ok.fillna(False).astype(bool)),
        handled_without_person=_rate(~df.escalated),
        handled_without_person_and_correct=_rate(~df.escalated & df.success),
        crashes=int(df.crashed.sum()),
        ungraded=int((~df.graded).sum()),
        latency_s_median=round(df.latency_ms.median() / 1000, 2),
        latency_s_median_ci=[None if v is None else round(v / 1000, 2) for v in bootstrap_median(df.latency_ms)],
        latency_s_p90=round(df.latency_ms.quantile(0.9) / 1000, 2),
        cost_usd_per_chat=round(df.cost_usd.mean(), 5),
        cost_usd_per_1000_chats=round(df.cost_usd.mean() * 1000, 2),
        cost_usd_per_successful_chat=round(df.cost_usd.sum() / len(ok), 5) if len(ok) else None,
        grading_cost_usd=round(df.grading_cost_usd.sum(), 4),
    )
    return s


HEADLINE = [  # (column, label, how to show it)
    ("task_success", "Task success", "rate"),
    ("request_type_accuracy", "Request type accuracy", "rate"),
    ("escalation_recall", "Escalation recall", "rate"),
    ("escalation_precision", "Escalation precision", "rate"),
    ("wrong_commitments", "Wrong commitments", "rate"),
    ("invented_facts", "Invented facts", "rate"),
    ("policy_failures", "Policy failures", "rate"),
    ("handled_without_person", "Handled without a person", "rate"),
    ("tone_ok", "Tone good (not in success)", "rate"),
    ("latency_s_median", "Median latency (s)", "num"),
    ("latency_s_p90", "p90 latency (s)", "num"),
    ("cost_usd_per_1000_chats", "Cost per 1,000 chats (USD)", "num"),
    ("cost_usd_per_successful_chat", "Cost per successful chat (USD)", "num"),
]


def fmt(v: Any, how: str) -> str:
    if v is None:
        return "n/a"
    if how == "rate":
        return f"{v['rate'] * 100:.1f}% ({v['k']}/{v['n']}; {v['ci_low'] * 100:.0f} to {v['ci_high'] * 100:.0f})"
    return f"{v}"


def headline_table(summaries: dict[str, dict], changes: dict[str, str]) -> pd.DataFrame:
    rows = []
    for name, s in summaries.items():
        row = {"setup": name, "change from full_agent": changes.get(name, "")}
        for key, label, how in HEADLINE:
            row[label] = fmt(s.get(key), how)
        rows.append(row)
    return pd.DataFrame(rows)


def slices(df: pd.DataFrame) -> pd.DataFrame:
    """Where one setup wins and loses: by difficulty, language, request type."""
    out = []
    for col in ("difficulty", "language", "gold_type"):
        for val, g in df.groupby(col):
            r = _rate(g.success)
            out.append(dict(slice=col, value=val, n=r["n"], success=r["rate"], ci_low=r["ci_low"], ci_high=r["ci_high"],
                            missed_handoffs=int(g.missed_handoff.sum()), wrong_commitments=int(g.wrong_commitment.sum()),
                            invented_facts=int(g.invented.sum())))
    return pd.DataFrame(out)


def markdown(df: pd.DataFrame) -> str:
    """A plain markdown table (no extra package needed)."""
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines) + "\n"
