"""Error analysis: group every failed chat by what went wrong, and by where in the agent.

Why two views: "what went wrong" (a missed handoff, an invented fact) says how bad the
failure is for the business; "where" (the router, a desk, a check, the grader itself)
says who fixes it. A chat can have several problems, so the groups overlap.

The written analysis, with causes and fixes, is in docs/evaluation_results.md.
"""
from __future__ import annotations

import pandas as pd

# (column test, group name, part of the agent most likely responsible)
GROUPS = [
    (lambda r: r.crashed, "crash", "code"),
    (lambda r: r.missed_handoff, "missed handoff", "router + desk"),
    (lambda r: r.extra_handoff, "extra handoff", "router + desk"),
    (lambda r: r.queue_ok is False, "wrong queue", "handoff rules"),
    (lambda r: bool(r.unbacked_promises), "promise no tool backs (rule)", "desk + output check"),
    (lambda r: r.graded and r.wrong_commitment and not r.unbacked_promises, "wrong commitment (grader)", "desk + output check"),
    (lambda r: r.graded and r.invented, "invented fact (grader)", "desk"),
    (lambda r: bool(r.other_person_data), "another person's data", "desk + output check"),
    (lambda r: bool(r.own_data_unverified), "data before verification", "desk + tools"),
    (lambda r: not r.language_ok, "wrong language", "desk"),
    (lambda r: bool(r.time_or_person_claims), "response time or 'I am a person'", "desk / fixed replies"),
    (lambda r: r.graded and not r.resolved, "request not resolved (grader)", "desk"),
    (lambda r: r.graded and not bool(r.grader_policy_followed), "policy broken (grader)", "desk"),
    (lambda r: not r.graded and not r.crashed, "not graded (grader error)", "grader"),
]


def failure_groups(row: pd.Series) -> list[tuple[str, str]]:
    return [(name, where) for test, name, where in GROUPS if test(row)]


def failures(df: pd.DataFrame) -> pd.DataFrame:
    """One line per failed chat, with every group it falls in and the evidence."""
    rows = []
    for _, r in df[~df.success].iterrows():
        groups = failure_groups(r)
        rows.append(dict(
            setup=r.setup, id=r.id, gold_type=r.gold_type, pred_type=r.pred_type, difficulty=r.difficulty,
            language=r.language, adversarial_type=r.adversarial_type, gold_escalation=r.gold_escalation,
            escalated=r.escalated, path=r.path, queue=r.queue,
            groups="; ".join(g for g, _ in groups), where="; ".join(sorted({w for _, w in groups})),
            router_wrong=(r.type_correct is False),
            rule_evidence=" | ".join(x for x in (r.unbacked_promises, r.other_person_data, r.own_data_unverified,
                                                 r.time_or_person_claims) if x),
            grader_evidence=" | ".join(x for x in (r.resolved_reason, r.policy_reason, r.invented_reason,
                                                   r.commitment_reason) if isinstance(x, str) and x),
            rules_broken=r.rules_broken, reply=r.reply))
    return pd.DataFrame(rows)


def group_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Setups as columns, failure groups as rows: how often each problem happened."""
    rows = []
    for setup, g in df.groupby("setup", sort=False):
        counts = {name: 0 for _, name, _ in GROUPS}
        for _, r in g[~g.success].iterrows():
            for name, _ in failure_groups(r):
                counts[name] += 1
        rows.append(dict(setup=setup, failed_chats=int((~g.success).sum()), **counts))
    return pd.DataFrame(rows).set_index("setup").T.reset_index().rename(columns={"index": "problem"})
