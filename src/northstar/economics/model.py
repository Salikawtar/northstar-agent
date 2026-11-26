"""Northstar cost model (Phase 6, economics and decision memo).

Main idea: compare what a month of service chats costs today (people answer every chat) with
what it costs with the agent, for each model option, at 1,000 / 100,000 / 1,000,000 chats a
month. "Cost" includes the model calls, the people who still handle handed-off chats, the
servers and engineering time, AND the cost of the agent's mistakes. Break-even points and a
sensitivity table show which assumptions the decision depends on.

    python -m northstar.economics

Where the numbers come from (nothing measured is typed by hand here):
    src/northstar/evaluation/results/summary.json   cost per reply, containment, error rates (40 test chats)
    src/northstar/evaluation/results/per_chat.csv   which desk each chat went to (cost mix)
    src/northstar/evaluation/results/per_chat_validation.csv, outputs/results/redteam.csv,
    outputs/results/handwritten.csv                 evidence on expensive (money or coverage) promises
    outputs/results/*_validation.json               desk-level Haiku vs Sonnet costs (bigger-model table)
                                                    (outputs/ is rebuilt by `run_all.py results`; a committed
                                                    snapshot, results/side_inputs.json, is used without it)
    src/northstar/finetune/results/breakeven.json   server cost of the fine-tuned router (Neeraj)
    src/northstar/evaluation/results/summary_fresh.json, per_chat_fresh.csv
                                                    the fresh held-out set, shown beside the base case (fresh_check)
    src/northstar/evaluation/results/grader_check*.csv   the grader against two people (people_check)
    config/settings.yaml                            server price
    config/economics.yaml                           everything the tests cannot measure, with sources

Writes src/northstar/economics/results/ (see README.md in this folder).
"""
from __future__ import annotations

import copy
import functools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from northstar.config import ROOT, settings

EVAL = ROOT / "src" / "northstar" / "evaluation" / "results"
FINETUNE = ROOT / "src" / "northstar" / "finetune" / "results"
DESKS = ROOT / "outputs" / "results"
OUT = Path(__file__).parent / "results"

# The model options compared (brief: "cost estimates per task for a few model options").
# Each one is a setup that was run and graded on the same 40 test chats; only the router changes,
# except the single agent, which is the architecture baseline.
OPTIONS = {
    "small_prompted": ("full_agent", "Small prompted router (Haiku 5.5), recommended agent"),
    "large_prompted": ("full_agent_router_sonnet", "Large prompted router (Sonnet 5.5)"),
    "finetuned": ("full_agent_router_finetuned", "Fine-tuned router (XLM-RoBERTa)"),
    "single_agent": ("single_agent", "Single Sonnet agent, no router (baseline)"),
    # Same agent, same measured numbers, but during the pilot a person approves every billing and
    # warranty reply before it is sent, so an expensive promise cannot reach a customer.
    "small_prompted_pilot": ("full_agent", "Recommended agent, person approves billing and warranty replies (pilot)"),
}
RECOMMENDED = "small_prompted"


# ---------------------------------------------------------------- inputs

def assumptions() -> dict:
    with open(ROOT / "config" / "economics.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def measured() -> dict:
    """Per option: the measured numbers the model needs, read from the final evaluation."""
    s = json.loads((EVAL / "summary.json").read_text(encoding="utf-8"))["setups"]
    out = {}
    for key, (setup, label) in OPTIONS.items():
        m = s[setup]
        n = m["n"]
        out[key] = {
            "setup": setup, "label": label, "n": n,
            "cost_per_reply": m["cost_usd_per_chat"],
            "cost_per_successful_reply": m["cost_usd_per_successful_chat"],
            "task_success": m["task_success"]["rate"],
            "handled_alone": m["handled_without_person"]["rate"],
            "handled_alone_correct": m["handled_without_person_and_correct"]["rate"],
            "handled_alone_correct_ci": [m["handled_without_person_and_correct"]["ci_low"],
                                         m["handled_without_person_and_correct"]["ci_high"]],
            "handled_alone_correct_k": m["handled_without_person_and_correct"]["k"],
            "handled_alone_k": m["handled_without_person"]["k"],
            "wrong_commitment": m["wrong_commitments"]["rate"],
            "wrong_commitment_k": m["wrong_commitments"]["k"],
            "wrong_commitment_upper": m["wrong_commitments"]["ci_high"],
            "invented": m["invented_facts"]["rate"],
            "invented_k": m["invented_facts"]["k"],
            "invented_upper": m["invented_facts"]["ci_high"],
            "missed_handoffs": m["missed_handoffs"],
            "missed_handoff_rate": m["missed_handoffs"] / n,
            "latency_s_median": m["latency_s_median"],
        }
    return out


DESK_FILES = ["booking_status_claude-haiku-5.5_v3_low_validation", "booking_status_claude-sonnet-5.5_v3_low_validation",
              "billing_lease_claude-haiku-5.5_v2_low_validation", "billing_lease_claude-sonnet-5.5_v2_medium_validation"]
SNAPSHOT = OUT / "side_inputs.json"


@functools.lru_cache(maxsize=1)
def side_inputs() -> dict:
    """Counts the model needs from outputs/results/ (red team, hand-written chats, desk runs).

    outputs/ is not in git: `python run_all.py results` rebuilds it from the recordings. When it is
    there, the counts are read from it and saved to results/side_inputs.json (committed); on a fresh
    clone without it, that snapshot is used, so this module runs on its own."""
    needed = [DESKS / "redteam.csv", DESKS / "handwritten.csv"] + [DESKS / f"{f}.json" for f in DESK_FILES]
    if not all(p.exists() for p in needed):
        if not SNAPSHOT.exists():
            raise FileNotFoundError("outputs/results/ is missing: run `python run_all.py results` first.")
        print(f"(outputs/results/ not found: using the committed snapshot {SNAPSHOT.name})")
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    red = pd.read_csv(DESKS / "redteam.csv")
    hw = pd.read_csv(DESKS / "handwritten.csv")
    need = hw[hw.handoff.notna()]
    desks = {}
    for f in DESK_FILES:
        d = json.loads((DESKS / f"{f}.json").read_text(encoding="utf-8"))
        desks[f] = {k: d[k] for k in ("n", "cost_usd_per_chat", "bookings_made", "handoff_recall", "replies_with_unbacked_promise")}
    out = {"redteam": {"n": len(red), "attack_succeeded": int(red.attack_succeeded.astype(bool).sum()),
                       "not_handed_to_person": int((~red.handed_to_person.astype(bool)).sum())},
           "handwritten": {"n": len(hw), "failed": int((~hw.passed.astype(bool)).sum()),
                           "expect_handoff": len(need), "expect_handoff_failed": int((~need.passed.astype(bool)).sum())},
           "desks": desks}
    OUT.mkdir(exist_ok=True)
    SNAPSHOT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def high_severity_evidence() -> dict:
    """Expensive promises (money, coverage, a free loaner, a waiver) that reached a customer.

    Counted on every reply of the recommended agent that was checked for them: the 40 test chats
    and 30 validation chats (rule check for unbacked promises), the 75 red-team attacks (an attack
    "succeeds" if the agent gives in, policy pressure and warranty fraud included) and the 40
    hand-written chats (each one fails if a promise check fails). None of the 12 wrong commitments
    the grader found across all test setups was about money: they were callbacks, a contact
    promise or a claim number (see results/mistakes_seen.csv)."""
    test = pd.read_csv(EVAL / "per_chat.csv")
    val = pd.read_csv(EVAL / "per_chat_validation.csv")
    side = side_inputs()
    t = test[test.setup == "full_agent"]
    v = val[val.setup == "full_agent"]
    sources = {
        "test chats (rule check)": (int(t.unbacked_promises.notna().sum()), len(t)),
        "validation chats (rule check)": (int(v.unbacked_promises.notna().sum()), len(v)),
        "red-team attacks (attack succeeded)": (side["redteam"]["attack_succeeded"], side["redteam"]["n"]),
        "hand-written chats (failed)": (side["handwritten"]["failed"], side["handwritten"]["n"]),
    }
    k = sum(a for a, _ in sources.values())
    n = sum(b for _, b in sources.values())
    return {"k": k, "n": n, "by_source": {name: {"k": a, "n": b} for name, (a, b) in sources.items()},
            "measured": k / n, "jeffreys_mean": (k + 0.5) / (n + 1), "wilson_upper_95": wilson(k, n)[1],
            "rule_of_three": 3 / n if k == 0 else None}


def handoff_evidence() -> dict:
    """Chats that needed a person and did not get one, for the recommended agent, on every set that
    checks it: test and validation chats (gold escalation), red-team attacks (all must go to a
    person) and the hand-written chats that expect a handoff (each fails if it is missed)."""
    test = pd.read_csv(EVAL / "per_chat.csv")
    val = pd.read_csv(EVAL / "per_chat_validation.csv")
    side = side_inputs()
    t, v = test[test.setup == "full_agent"], val[val.setup == "full_agent"]
    sources = {
        "test chats": (int(t.missed_handoff.astype(bool).sum()), int(t.gold_escalation.astype(bool).sum())),
        "validation chats": (int(v.missed_handoff.astype(bool).sum()), int(v.gold_escalation.astype(bool).sum())),
        "red-team attacks": (side["redteam"]["not_handed_to_person"], side["redteam"]["n"]),
        "hand-written chats": (side["handwritten"]["expect_handoff_failed"], side["handwritten"]["expect_handoff"]),
    }
    k = sum(a for a, _ in sources.values())
    n = sum(b for _, b in sources.values())
    need_share = float(t.gold_escalation.astype(bool).mean())       # share of ordinary chats that need a person
    return {"k": k, "n": n, "by_source": {name: {"missed": a, "needed_a_person": b} for name, (a, b) in sources.items()},
            "share_of_chats_needing_a_person": round(need_share, 3),
            "jeffreys_mean_per_chat_needing_person": (k + 0.5) / (n + 1),
            "wilson_upper_per_chat_needing_person": wilson(k, n)[1]}


def mistakes_seen() -> pd.DataFrame:
    """Every wrong commitment the grader found on the test chats, in every setup, for the severity check."""
    d = pd.read_csv(EVAL / "per_chat.csv")
    w = d[d.wrong_commitment.astype(bool)][["setup", "id", "gold_type", "commitment_reason", "unbacked_promises"]]
    w = w.assign(severity=np.where(w.unbacked_promises.notna(), "high (money or coverage)", "low (callback, contact, claim number)"))
    return w.reset_index(drop=True)


@functools.lru_cache(maxsize=1)
def desk_mix() -> dict:
    """Share of chats each part of the recommended agent answered on the test chats."""
    d = pd.read_csv(EVAL / "per_chat.csv")
    f = d[d.setup == "full_agent"]
    return (f.path.value_counts(normalize=True)).round(4).to_dict()


# ---------------------------------------------------------------- unit costs

def usd(cad: float, a: dict) -> float:
    return cad / a["currency"]["cad_per_usd"]


def advisor_usd_per_minute(a: dict) -> float:
    sq = a["status_quo"]
    return usd(sq["advisor_wage_cad_per_hour"] * (1 + sq["payroll_overhead"]), a) / 60


def mistake_costs(a: dict) -> dict:
    """What one mistake of each kind costs the dealership, in USD."""
    m, per_min = a["mistakes"], advisor_usd_per_minute(a)
    low = m["recovery_minutes"] * per_min + usd(m["goodwill_cad"], a)
    dispute = m["dispute_minutes"] * per_min
    return {
        # A promised callback, a wrong date or a made-up claim number: someone calls the customer back.
        "low_severity": low,
        "invented_fact": low,
        # The planning value for an expensive promise is the warranty case (largest of the three
        # examples below): the dealership honours a repair it should not have promised.
        "high_severity": m["repair_usd"] + dispute,
        "missed_handoff": m["missed_handoff_usd"],
        "examples": {
            "wrongly promised covered repair": m["repair_usd"] + dispute,
            "wrongly promised free loaner": usd(m["loaner_cad_per_day"] * m["loaner_days"], a) + dispute,
            "chatbot promise ordered paid by a tribunal (Moffatt v. Air Canada)": usd(m["tribunal_award_cad"], a) + dispute,
            "missed callback or wrong date (recovery call)": low,
            "missed handoff (safety, legal or dispute chat)": m["missed_handoff_usd"],
        },
    }


# ---------------------------------------------------------------- monthly cost

def status_quo(volume: int, a: dict) -> dict:
    sq, per_min = a["status_quo"], advisor_usd_per_minute(a)
    people = volume * sq["minutes_per_chat"] * per_min
    errors = volume * sq["wrong_commitment_rate"] * mistake_costs(a)["low_severity"]
    return {"people": people, "mistakes": errors, "total": people + errors}


def engineer_hours(volume: int, a: dict) -> float:
    for ceiling, hours in a["fixed_monthly"]["engineer_hours_by_volume"]:
        if volume <= ceiling:
            return hours
    return a["fixed_monthly"]["engineer_hours_by_volume"][-1][1]


@functools.lru_cache(maxsize=1)
def finetune_breakeven() -> dict:
    return json.loads((FINETUNE / "breakeven.json").read_text(encoding="utf-8"))


def fixed_costs(volume: int, a: dict, option: str, hosting: dict) -> dict:
    """Costs that do not depend on each chat: servers, monitoring, engineering, build paid back."""
    f = a["fixed_monthly"]
    server_month = hosting["usd_per_hour"] * hosting["hours_per_month"]
    servers = max(f["app_servers_min"], math.ceil(volume / f["chats_per_app_server"]))
    eng_rate = usd(f["engineer_wage_cad_per_hour"] * (1 + a["status_quo"]["payroll_overhead"]), a)
    out = {
        "app_servers": servers * server_month,
        "monitoring": f["monitoring_usd"] + volume * f["monitoring_usd_per_chat"],
        "evaluation_runs": f["evaluation_usd"],
        "engineering": engineer_hours(volume, a) * eng_rate,
        "build_paid_back": f["build_hours"] * eng_rate / f["build_payback_months"],
    }
    if option == "finetuned":
        # Neeraj's break-even: one CPU server all month plus a quarterly retrain, from the same price file.
        ft = finetune_breakeven()
        n = max(hosting["servers"], math.ceil(volume / ft["capacity_chats_per_month_per_server"]))
        out["finetuned_router_server"] = n * ft["base_case"]["monthly_fixed_usd"]
    return out


def agent_month(volume: int, a: dict, m: dict, option: str, high_rate: float, hosting: dict) -> dict:
    """One month with the agent. m = measured numbers of this option."""
    op, per_min = a["agent_operation"], advisor_usd_per_minute(a)
    chat_person = a["status_quo"]["minutes_per_chat"] * per_min      # one chat handled by a person
    cost = mistake_costs(a)
    pilot = option.endswith("_pilot")
    if pilot:
        high_rate = 0.0                                               # a person approves every money reply
    handed = 1 - m["handled_alone"]                                   # went to a person
    closed_wrong = m["handled_alone"] - m["handled_alone_correct"]    # finished alone but wrong: comes back
    var = {
        "model_calls": volume * m["cost_per_reply"] * op["replies_per_conversation"] * (1 + op["retry_overhead"]),
        "people_handoffs": volume * handed * chat_person * op["handoff_time_factor"],
        "people_rework": volume * closed_wrong * chat_person * op["failed_containment_rework"],
        "people_review": volume * m["handled_alone"] * op["qa_review_share"] * op["qa_minutes_per_review"] * per_min,
        "mistakes_wrong_commitment": volume * m["wrong_commitment"] * cost["low_severity"],
        "mistakes_invented_fact": volume * m["invented"] * cost["invented_fact"],
        "mistakes_missed_handoff": volume * m["missed_handoff_rate"] * cost["missed_handoff"],
        "mistakes_expensive_promise": volume * high_rate * cost["high_severity"],
    }
    if pilot:
        # Share of chats a money desk answers: the test chats by default, or the set these rates come from.
        money_share = m.get("money_desk_share", sum(desk_mix().get(d, 0) for d in a["pilot"]["money_desks"]))
        var["people_approval"] = volume * money_share * a["pilot"]["approval_minutes"] * per_min
    fixed = fixed_costs(volume, a, option, hosting)
    total = sum(var.values()) + sum(fixed.values())
    return {**var, **fixed, "total": total}


def saving(volume: int, a: dict, m: dict, option: str, high_rate: float, hosting: dict) -> float:
    return status_quo(volume, a)["total"] - agent_month(volume, a, m, option, high_rate, hosting)["total"]


# ---------------------------------------------------------------- break-even points

def breakeven_volume(a: dict, m: dict, option: str, high_rate: float, hosting: dict) -> int | None:
    """Smallest monthly volume above which the agent stays cheaper than people alone (up to 10M)."""
    grid = np.unique(np.round(np.geomspace(100, 1e7, 3000), -1)).astype(int)
    ok = np.array([saving(int(v), a, m, option, high_rate, hosting) > 0 for v in grid])
    if not ok[-1]:
        return None
    last_bad = np.where(~ok)[0]
    v = int(grid[last_bad[-1] + 1]) if len(last_bad) else int(grid[0])
    return int(math.ceil(v / 100) * 100)


def breakeven_rate(volume: int, a: dict, m: dict, option: str, hosting: dict, kind: str) -> float | None:
    """Mistake rate at which the saving at this volume falls to zero.
    kind = 'high': expensive promises (measured 0 so far); kind = 'low': callbacks and wrong facts."""
    base = saving(volume, a, m, option, 0.0, hosting)
    if base <= 0:
        return None                     # the agent loses at this volume even with no expensive mistakes
    c = mistake_costs(a)
    if kind == "high":
        return base / (volume * c["high_severity"])
    return m["wrong_commitment"] + base / (volume * c["low_severity"])


def _r(x, nd):
    return None if x is None else round(x, nd)


def breakeven_containment(volume: int, a: dict, m: dict, option: str, hosting: dict) -> float | None:
    """Share of chats the agent must finish alone and correctly for the saving to reach zero
    (the share finished alone but wrong is held at its measured level)."""
    per_min = advisor_usd_per_minute(a)
    chat_person = a["status_quo"]["minutes_per_chat"] * per_min * a["agent_operation"]["handoff_time_factor"]
    s = saving(volume, a, m, option, 0.0, hosting)
    if s <= 0:
        return None
    return m["handled_alone_correct"] - s / (volume * chat_person)


def warranty_automation(a: dict) -> dict:
    """If the agent approved warranty claims itself, the saving per claim is the
    reviewer's time; each wrong approval costs a honoured repair. Break-even = saving / cost."""
    w, per_min = a["warranty_automation"], advisor_usd_per_minute(a)
    cost = mistake_costs(a)["high_severity"]
    rows = {}
    for name, minutes in [("base", w["review_minutes_saved"]),
                          ("low", w["review_minutes_range"][0]), ("high", w["review_minutes_range"][1])]:
        saved = minutes * per_min
        rows[name] = {"review_minutes": minutes, "saving_per_claim_usd": round(saved, 2),
                      "breakeven_wrong_approval_rate": round(saved / cost, 4),
                      "claims_per_wrong_approval_to_break_even": int(round(cost / saved))}
    return rows


# ---------------------------------------------------------------- bigger or smaller model

def bigger_model(a: dict, mes: dict, mix: dict, volume: int) -> pd.DataFrame:
    """Is the larger model worth its extra cost, desk by desk?
    A larger model pays if it avoids one mistake every (cost of that mistake / extra cost) chats."""
    rpc = a["agent_operation"]["replies_per_conversation"]
    c = mistake_costs(a)
    desk = lambda f: side_inputs()["desks"][f]  # noqa: E731
    ft = pd.read_csv(FINETUNE / "comparison_table.csv").set_index("router")
    rows = []

    def row(part, small, large, share, mistake, mistake_cost, quality, decision):
        extra = (large - small) * rpc                        # per conversation on that desk
        rows.append({
            "part": part, "small_usd_per_reply": round(small, 6), "large_usd_per_reply": round(large, 6),
            "extra_usd_per_conversation": round(extra, 4), "share_of_chats": round(share, 3),
            f"extra_usd_per_month_at_{volume}": round(extra * share * volume, 0),
            "mistake_guarded": mistake, "mistake_cost_usd": round(mistake_cost, 2),
            "one_avoided_mistake_pays_for_conversations": int(round(mistake_cost / extra)) if extra > 0 else None,
            "measured_quality_difference": quality, "decision": decision})

    row("Router (every chat)", ft.loc["Small prompted (Haiku)", "cost_usd_per_chat"],
        ft.loc["Large prompted (Sonnet)", "cost_usd_per_chat"], 1.0, "missed handoff", c["missed_handoff"],
        "Sonnet: type accuracy 77.5% vs 82.5%; in the agent 1 missed handoff and 2 wrong commitments vs 0 and 1",
        "Keep Haiku: costs more and was not better")
    b_s, b_l = desk("booking_status_claude-haiku-5.5_v3_low_validation"), desk("booking_status_claude-sonnet-5.5_v3_low_validation")
    row("Booking and status desk", b_s["cost_usd_per_chat"], b_l["cost_usd_per_chat"], mix.get("booking_status", 0),
        "missed callback or wrong date", c["low_severity"],
        f"Same handoff recall and 0 unbacked promises on {b_s['n']} validation chats; Haiku made {b_s['bookings_made']} booking, Sonnet {b_l['bookings_made']}",
        "Keep Haiku: a mistake here is cheap, so the larger model must avoid one every few hundred chats, and it avoided none")
    l_s, l_l = desk("billing_lease_claude-haiku-5.5_v2_low_validation"), desk("billing_lease_claude-sonnet-5.5_v2_medium_validation")
    row("Billing and lease desk", l_s["cost_usd_per_chat"], l_l["cost_usd_per_chat"], mix.get("billing_lease", 0),
        "expensive promise (refund, waiver, credit)", c["high_severity"],
        f"Tie on {l_s['n']} validation chats (100% handoff recall, 0 unbacked promises); Haiku looped on tools (3x the tool calls)",
        "Keep Sonnet (D-25): one avoided money mistake pays for tens of thousands of chats, and 7 chats cannot show Haiku is as safe")
    w = json.loads((EVAL / "summary.json").read_text(encoding="utf-8"))["setups"]
    row("Warranty desk, high vs medium effort", w["full_agent"]["cost_usd_per_chat"], w["full_agent_warranty_high"]["cost_usd_per_chat"],
        mix.get("warranty_recall", 0), "expensive promise (coverage)", c["high_severity"],
        "High effort on the test chats: 65.0% vs 70.0% success, 2 invented facts vs 1, same wrong commitments",
        "Keep medium (D-24): the extra effort bought no safety")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- sensitivity and uncertainty

def _set(a: dict, path: str, value) -> dict:
    b = copy.deepcopy(a)
    keys = path.split(".")
    d = b
    for k in keys[:-1]:
        d = d[k]
    d[keys[-1]] = value
    return b


def sensitivity(a: dict, m: dict, hosting: dict, ev: dict, ho: dict, volumes: list[int]) -> pd.DataFrame:
    """One assumption at a time, low and high, everything else at base."""
    sq, op, mi, fx = a["status_quo"], a["agent_operation"], a["mistakes"], a["fixed_monthly"]
    tests = [
        ("Advisor minutes per chat", "a", "status_quo.minutes_per_chat", sq["minutes_range"]),
        ("Advisor wage (C$/h)", "a", "status_quo.advisor_wage_cad_per_hour", sq["advisor_wage_range"]),
        ("Replies per conversation", "a", "agent_operation.replies_per_conversation", op["replies_range"]),
        ("Handed-off chat time (share of a full chat)", "a", "agent_operation.handoff_time_factor", op["handoff_time_range"][::-1]),
        ("Recovery minutes per small mistake", "a", "mistakes.recovery_minutes", mi["recovery_minutes_range"][::-1]),
        ("Goodwill per small mistake (C$)", "a", "mistakes.goodwill_cad", mi["goodwill_range_cad"][::-1]),
        ("People's own wrong-promise rate", "a", "status_quo.wrong_commitment_rate", sq["wrong_commitment_range"]),
        ("Engineering hours (x base)", "eng", None, fx["engineer_hours_scale_range"][::-1]),
        ("Finished alone and correct (test 95% range)", "m", "handled_alone_correct", m["handled_alone_correct_ci"]),
        ("Small wrong commitments (test 95% range)", "m", "wrong_commitment", [m["wrong_commitment_upper"], wilson(m["wrong_commitment_k"], m["n"])[0]]),
        ("Invented facts (test 95% range)", "m", "invented", [m["invented_upper"], wilson(m["invented_k"], m["n"])[0]]),
        ("Expensive promises (0 in 185; Wilson upper)", "high", None, [ev["wilson_upper_95"], 0.0]),
        # 0 missed in 132 chats that needed a person: the upper end, at the base cost of a miss.
        ("Missed handoffs per chat (0 in 132; Wilson upper)", "m", "missed_handoff_rate",
         [ho["wilson_upper_per_chat_needing_person"] * ho["share_of_chats_needing_a_person"], 0.0]),
    ]
    rows = []
    for label, kind, path, (lo, hi) in tests:
        r = {"assumption": label, "pessimistic": lo, "optimistic": hi}
        for v in volumes:
            for tag, val in (("pessimistic", lo), ("optimistic", hi)):
                aa, mm, hr = a, m, 0.0
                if kind == "a":
                    aa = _set(a, path, val)
                elif kind == "eng":
                    aa = copy.deepcopy(a)
                    aa["fixed_monthly"]["engineer_hours_by_volume"] = [[c, h * val] for c, h in fx["engineer_hours_by_volume"]]
                    aa["fixed_monthly"]["build_hours"] = fx["build_hours"] * val
                elif kind == "m":
                    mm = {**m, path: val}
                else:
                    hr = val
                r[f"saving_{tag}_{v}"] = round(saving(v, aa, mm, RECOMMENDED, hr, hosting), 0)
        rows.append(r)
    df = pd.DataFrame(rows)
    v = volumes[-1]
    df["swing"] = (df[f"saving_optimistic_{v}"] - df[f"saving_pessimistic_{v}"]).abs()
    return df.sort_values("swing", ascending=False).drop(columns="swing").reset_index(drop=True)


def monte_carlo(a: dict, m: dict, hosting: dict, ev: dict, ho: dict, volumes: list[int]) -> dict:
    """How sure are we that the agent saves money, given a few hundred test chats?

    Each measured rate is drawn from its Beta posterior (Jeffreys prior: k events in n chats);
    the assumptions stay at base. Containment and small mistakes come from the 40 test chats;
    missed handoffs and expensive promises, which were never seen, from every set that checks
    them (ho and ev). Two designs: the agent as built, and the pilot, where a person approves the
    billing and warranty replies, so an expensive promise cannot reach a customer."""
    rng = np.random.default_rng(settings()["project"]["seed"])
    n, draws = m["n"], a["monte_carlo"]["draws"]
    beta = lambda k, nn: rng.beta(k + 0.5, nn - k + 0.5, draws)  # noqa: E731
    alone = beta(m["handled_alone_k"], n)
    correct_share = rng.beta(m["handled_alone_correct_k"] + 0.5,
                             m["handled_alone_k"] - m["handled_alone_correct_k"] + 0.5, draws)
    wc, inv = beta(m["wrong_commitment_k"], n), beta(m["invented_k"], n)
    share = ho["share_of_chats_needing_a_person"]
    extra = a["monte_carlo"]["clean_pilot_chats"]
    designs = [
        ("as_built", RECOMMENDED, 0),
        ("pilot_with_approval", "small_prompted_pilot", 0),
        # After a clean pilot of `extra` chats: no missed handoff, no expensive promise caught by the approver.
        # This is the gate for removing the approval step.
        (f"as_built_after_clean_pilot_of_{extra}", RECOMMENDED, extra),
    ]
    out = {}
    for design, option, clean in designs:
        miss = beta(ho["k"], ho["n"] + round(clean * share)) * share
        high = beta(ev["k"], ev["n"] + clean)
        out[design] = {}
        for v in volumes:
            s = np.array([saving(v, a, {**m, "handled_alone": alone[i], "handled_alone_correct": alone[i] * correct_share[i],
                                        "wrong_commitment": wc[i], "invented": inv[i], "missed_handoff_rate": miss[i]},
                                 option, high[i], hosting) for i in range(draws)])
            out[design][str(v)] = {"probability_saving_positive": round(float((s > 0).mean()), 3),
                                   "saving_p05": round(float(np.percentile(s, 5)), 0),
                                   "saving_median": round(float(np.median(s)), 0),
                                   "saving_p95": round(float(np.percentile(s, 95)), 0)}
    return out


# ---------------------------------------------------------------- checks beside the base case

def fresh_check(a: dict, m: dict, hosting: dict, volumes: list[int]) -> dict | None:
    """The fresh held-out set (D-33) next to the base case.

    The base case stays on the 40 test chats: every break-even, range and draw above was built on
    them. But the test chats were read during the error analysis, and the fresh set (31 chats made
    after every fix, run once) is the only set nobody could tune to. This block re-prices the
    recommended agent with the rates measured on it and changes nothing else, so the memo can show
    both side by side instead of the kinder one.

    Missed handoffs are priced two ways, because their cost is our least certain assumption: not
    priced, and at the price per miss that every other option in the model pays. The pilot month
    is priced the same two ways, with the share of fresh chats that a money desk answered."""
    f_sum, f_chat = EVAL / "summary_fresh.json", EVAL / "per_chat_fresh.csv"
    if not (f_sum.exists() and f_chat.exists()):
        return None                                  # the model still runs where the fresh set was never run
    s = json.loads(f_sum.read_text(encoding="utf-8"))["setups"].get(m["setup"])
    if s is None:
        return None
    d = pd.read_csv(f_chat)
    d = d[d.setup == m["setup"]]
    n, rec = s["n"], s["escalation_recall"]
    alone, correct = s["handled_without_person"]["k"], s["handled_without_person_and_correct"]["k"]
    attacks = d[d.adversarial_type.fillna("").astype(str) != ""]
    missed = d[d.missed_handoff.astype(bool)]
    # Counts over n, not the summary's rounded rates: with 31 chats the third decimal moves the result.
    rates = {**m, "cost_per_reply": s["cost_usd_per_chat"], "handled_alone": alone / n,
             "handled_alone_correct": correct / n, "wrong_commitment": s["wrong_commitments"]["k"] / n,
             "invented": s["invented_facts"]["k"] / n, "missed_handoff_rate": s["missed_handoffs"] / n,
             "money_desk_share": float(d.path.isin(a["pilot"]["money_desks"]).mean())}
    # How many of these chats need a person only because the two reviewers said so: the share that needs
    # a person drives containment, and the review moved it more than anything the agent did.
    frozen = ROOT / "data" / "fresh" / "FROZEN.json"
    changes = json.loads(frozen.read_text(encoding="utf-8")).get("label_changes", []) if frozen.exists() else []
    kept = set(d.id.astype(str))
    added = sum(1 for c in changes if c.split(":")[0] in kept and "needs_escalation False -> True" in c)
    removed = sum(1 for c in changes if c.split(":")[0] in kept and "needs_escalation True -> False" in c)
    op = a["agent_operation"]
    out = {
        "setup": m["setup"], "chats": n,
        "task_success": s["task_success"]["rate"], "task_success_k": s["task_success"]["k"],
        "handoffs_needed": rec["n"], "handoffs_made": rec["k"], "missed_handoffs": s["missed_handoffs"],
        "missed_handoffs_by_desk": {str(k): int(v) for k, v in missed.path.value_counts().items()},
        "missed_handoff_chats": sorted(missed.id.astype(str)),
        "share_needing_a_person": round(rec["n"] / n, 3),
        "handoffs_added_by_review": added - removed,
        "handoffs_needed_before_review": rec["n"] - added + removed,
        "share_needing_a_person_before_review": round((rec["n"] - added + removed) / n, 3),
        "finished_alone": alone, "finished_alone_correct": correct,
        "finished_alone_correct_rate": round(correct / n, 3),
        "wrong_commitments": s["wrong_commitments"]["k"], "invented_facts": s["invented_facts"]["k"],
        "expensive_promises_rule_check": int(d.unbacked_promises.notna().sum()),
        "attack_chats": len(attacks), "attack_chats_passed_to_a_person": int(attacks.escalated.astype(bool).sum()),
        "latency_s_median": s["latency_s_median"],
        "model_usd_per_conversation": round(s["cost_usd_per_chat"] * op["replies_per_conversation"] * (1 + op["retry_overhead"]), 4),
        "missed_handoff_usd": mistake_costs(a)["missed_handoff"],
        "saving_at": {}, "saving_pct_at": {}, "usd_per_chat_at": {},
        # The decision asked is the pilot, so the pilot month is priced with these rates too.
        "pilot": {"chats_per_month": a["pilot"]["chats_per_month"],
                  "money_desk_share": round(rates["money_desk_share"], 3), "saving_usd_per_month": {}},
    }
    cases = (("missed_handoffs_not_priced", {**rates, "missed_handoff_rate": 0.0}), ("missed_handoffs_priced", rates))
    for v in volumes:
        today = status_quo(v, a)["total"]
        for tag, mm in cases:
            cost = agent_month(v, a, mm, RECOMMENDED, 0.0, hosting)["total"]
            out["saving_at"].setdefault(str(v), {})[tag] = round(today - cost, 0)
            out["saving_pct_at"].setdefault(str(v), {})[tag] = round(100 * (today - cost) / today, 1)
            out["usd_per_chat_at"].setdefault(str(v), {})[tag] = round(cost / v, 3)
    for tag, mm in cases:
        out["pilot"]["saving_usd_per_month"][tag] = round(
            saving(a["pilot"]["chats_per_month"], a, mm, "small_prompted_pilot", 0.0, hosting), 0)
    return out


def people_check() -> dict | None:
    """The model grader against the two team members who labelled 80 replies blind
    (evaluation/human_check.py). Read here, so the memo quotes the result files and not a typed number."""
    f_setup, f_all = EVAL / "grader_check_by_setup.csv", EVAL / "grader_check.csv"
    if not (f_setup.exists() and f_all.exists()):
        return None                                  # the hand labels are optional for the cost model
    by = pd.read_csv(f_setup).set_index("setup")
    g = pd.read_csv(f_all)
    overall = g[g.question.str.startswith("overall") & g.compared.str.startswith("model grader")]
    main = by.loc[OPTIONS[RECOMMENDED][0]]
    return {"replies_checked": int(overall.n.iloc[0]),
            "kappa_overall_success": [round(float(k), 2) for k in overall.kappa],
            "main_agent_success_by_people": [float(main.person), float(main.second_person)],
            "main_agent_success_by_grader": float(main.final_grade)}


# ---------------------------------------------------------------- build everything

def build() -> dict:
    a = assumptions()
    hosting = settings()["finetuned_router_hosting"]
    mes = measured()
    ev = high_severity_evidence()
    ho = handoff_evidence()
    mix = desk_mix()
    volumes = a["volumes"]
    northstar = a["northstar_volume"]
    all_volumes = sorted(set(volumes + [northstar]))
    rpc = a["agent_operation"]["replies_per_conversation"]
    OUT.mkdir(exist_ok=True)

    # 1. Unit economics per option.
    unit = []
    sq_chat = status_quo(1, a)["total"]
    unit.append({"option": "status_quo", "label": "People answer every chat (today)",
                 "model_usd_per_reply": None, "model_usd_per_successful_reply": None,
                 "model_usd_per_conversation": 0.0, "success_rate": a["status_quo"]["first_contact_resolution"],
                 "handled_alone_correct": 0.0, "all_in_usd_per_chat_at_100000": round(sq_chat, 3),
                 "all_in_usd_per_successful_chat_at_100000": round(sq_chat / a["status_quo"]["first_contact_resolution"], 3),
                 "all_in_usd_per_chat_without_missed_handoff_cost": round(sq_chat, 3)})
    for key, m in mes.items():
        c100 = agent_month(100_000, a, m, key, ev["measured"], hosting)
        tot = c100["total"] / 100_000
        no_miss = (c100["total"] - c100["mistakes_missed_handoff"]) / 100_000
        unit.append({"option": key, "label": m["label"],
                     "model_usd_per_reply": m["cost_per_reply"], "model_usd_per_successful_reply": m["cost_per_successful_reply"],
                     "model_usd_per_conversation": round(m["cost_per_reply"] * rpc * (1 + a["agent_operation"]["retry_overhead"]), 4),
                     "success_rate": m["task_success"], "handled_alone_correct": m["handled_alone_correct"],
                     "all_in_usd_per_chat_at_100000": round(tot, 3),
                     "all_in_usd_per_successful_chat_at_100000": round(tot / m["task_success"], 3),
                     "all_in_usd_per_chat_without_missed_handoff_cost": round(no_miss, 3)})
    unit = pd.DataFrame(unit)

    # 2. Volume scenarios with every cost line.
    rows = []
    for v in all_volumes:
        s = status_quo(v, a)
        rows.append({"chats_per_month": v, "option": "status_quo", "people_handoffs": round(s["people"], 0),
                     "mistakes_wrong_commitment": round(s["mistakes"], 0), "total": round(s["total"], 0),
                     "usd_per_chat": round(s["total"] / v, 3), "saving_vs_status_quo": 0.0, "saving_pct": 0.0})
        for key, m in mes.items():
            c = agent_month(v, a, m, key, ev["measured"], hosting)
            sav = s["total"] - c["total"]
            rows.append({"chats_per_month": v, "option": key, **{k: round(x, 0) for k, x in c.items()},
                         "usd_per_chat": round(c["total"] / v, 3), "saving_vs_status_quo": round(sav, 0),
                         "saving_pct": round(100 * sav / s["total"], 1)})
    scen = pd.DataFrame(rows).fillna(0)

    # 3. Cost of mistakes.
    costs = mistake_costs(a)
    mistakes = pd.DataFrame([{"mistake": k, "usd_per_event": round(x, 2)} for k, x in costs["examples"].items()])
    seen = mistakes_seen()

    # 4. Break-even points.
    m = mes[RECOMMENDED]
    be = {
        "volume": {k: breakeven_volume(a, mes[k], k, ev["measured"], hosting) for k in mes},
        "volume_with_expensive_promises_at_jeffreys_mean": breakeven_volume(a, m, RECOMMENDED, ev["jeffreys_mean"], hosting),
        "expensive_promise_rate": {str(v): _r(breakeven_rate(v, a, m, RECOMMENDED, hosting, "high"), 5) for v in all_volumes},
        "small_wrong_commitment_rate": {str(v): _r(breakeven_rate(v, a, m, RECOMMENDED, hosting, "low"), 4) for v in all_volumes},
        "containment": {str(v): _r(breakeven_containment(v, a, m, RECOMMENDED, hosting), 4) for v in all_volumes},
        # Rule of three: after n clean chats the 95% upper bound is about 3 / n.
        "clean_chats_needed_to_show_expensive_promises_below_breakeven":
            {str(v): (int(math.ceil(3 / r)) if (r := breakeven_rate(v, a, m, RECOMMENDED, hosting, "high")) else None) for v in all_volumes},
        "warranty_automation": warranty_automation(a),
        "finetuned_router_inside_agent": {
            "router_saving_usd_per_conversation": round((m["cost_per_reply"] - mes["finetuned"]["cost_per_reply"]) * rpc, 4),
            "containment_loss_points": round(100 * (m["handled_alone_correct"] - mes["finetuned"]["handled_alone_correct"]), 1),
            "people_cost_of_that_loss_usd_per_conversation": round(
                (m["handled_alone_correct"] - mes["finetuned"]["handled_alone_correct"]) * a["status_quo"]["minutes_per_chat"] * advisor_usd_per_minute(a), 3),
        },
        "finetuned_router_alone_vs_haiku_chats_per_month": json.loads((FINETUNE / "breakeven.json").read_text())["base_case"]["vs_haiku_chats_per_month"],
    }

    # 5. Larger or smaller model, sensitivity and uncertainty (the appendix of docs/economics.md).
    big = bigger_model(a, mes, mix, 100_000)
    sens = sensitivity(a, m, hosting, ev, ho, [northstar, 100_000])
    mc = monte_carlo(a, m, hosting, ev, ho, [northstar, 100_000])

    # Stress cases for the memo: every measured rate at the pessimistic end of its range.
    stress_m = {**m, "handled_alone_correct": m["handled_alone_correct_ci"][0],
                "wrong_commitment": m["wrong_commitment_upper"], "invented": m["invented_upper"]}
    stress = {str(v): {"expensive_promises_jeffreys": round(saving(v, a, m, RECOMMENDED, ev["jeffreys_mean"], hosting), 0),
                       "expensive_promises_wilson_upper": round(saving(v, a, m, RECOMMENDED, ev["wilson_upper_95"], hosting), 0),
                       "all_test_rates_pessimistic": round(saving(v, a, stress_m, RECOMMENDED, 0.0, hosting), 0),
                       "pilot_all_test_rates_pessimistic": round(saving(v, a, stress_m, "small_prompted_pilot", 0.0, hosting), 0)}
              for v in all_volumes}

    # Checks beside the base case: the fresh held-out set and the grader-vs-people check.
    fresh = fresh_check(a, m, hosting, [northstar, 100_000])
    people = people_check()

    per_min = advisor_usd_per_minute(a)
    summary = {
        "currency": "USD unless a field ends in _cad",
        "cad_per_usd": a["currency"]["cad_per_usd"],
        "advisor_usd_per_minute": round(per_min, 4),
        "status_quo_usd_per_chat": round(status_quo(1, a)["total"], 3),
        "status_quo_people_usd_per_chat": round(status_quo(1, a)["people"], 3),
        "recommended": RECOMMENDED,
        "measured": mes,
        "desk_mix": mix,
        "rules_only_share": round(mix.get("fast_path", 0) + mix.get("out_of_scope", 0), 3),
        "expensive_promise_evidence": ev,
        "handoff_evidence": ho,
        "mistake_costs": {k: round(v, 2) for k, v in costs.items() if k != "examples"},
        "breakeven": be,
        "stress_savings": stress,
        "monte_carlo": mc,
        "northstar_volume": northstar,
        "pilot": {"chats_per_month": a["pilot"]["chats_per_month"],
                  "saving_usd_per_month": round(saving(a["pilot"]["chats_per_month"], a, m, "small_prompted_pilot", 0.0, hosting), 0),
                  "approval_usd_per_month": round(agent_month(a["pilot"]["chats_per_month"], a, m, "small_prompted_pilot", 0.0, hosting)["people_approval"], 0),
                  "money_desk_share": round(sum(mix.get(d, 0) for d in a["pilot"]["money_desks"]), 3)},
        "saving_at": {str(v): {k: float(scen[(scen.chats_per_month == v) & (scen.option == k)].saving_vs_status_quo.iloc[0])
                               for k in mes} for v in all_volumes},
        "saving_pct_at": {str(v): {k: float(scen[(scen.chats_per_month == v) & (scen.option == k)].saving_pct.iloc[0])
                                   for k in mes} for v in all_volumes},
        # All-in cost per chat of the recommended agent at each volume (the memo quotes Northstar's own volume).
        "usd_per_chat_at": {str(v): float(scen[(scen.chats_per_month == v) & (scen.option == RECOMMENDED)].usd_per_chat.iloc[0])
                            for v in all_volumes},
        "fresh_set_check": fresh,
        "grader_vs_people": people,
    }

    unit.to_csv(OUT / "unit_economics.csv", index=False)
    scen.to_csv(OUT / "scenarios.csv", index=False)
    mistakes.to_csv(OUT / "mistake_costs.csv", index=False)
    seen.to_csv(OUT / "mistakes_seen.csv", index=False)
    big.to_csv(OUT / "bigger_model.csv", index=False)
    sens.to_csv(OUT / "sensitivity.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    write_tables(summary, unit, scen, mistakes, big, sens, a)
    chart(a, mes, ev, hosting, be)
    return summary


# ---------------------------------------------------------------- report tables and chart

def _money(x: float) -> str:
    return f"${x:,.0f}" if abs(x) >= 100 else f"${x:,.2f}"


def write_tables(summary, unit, scen, mistakes, big, sens, a) -> None:
    """results/tables.md: the tables pasted into report page 7 and the appendix, built from the
    same numbers as the CSV files so the report and the code cannot disagree."""
    L = ["# Economics tables (generated by `python -m northstar.economics`; do not edit by hand)", ""]
    L += ["## Unit economics (cost per chat at 100,000 chats a month, USD)", "",
          "| Option | Model cost per conversation | Success rate | Finished alone and correct | All-in cost per chat | All-in cost per successful chat | All-in, missed handoffs not priced |",
          "|---|---|---|---|---|---|---|"]
    for _, r in unit.iterrows():
        L.append(f"| {r.label} | ${r.model_usd_per_conversation:.4f} | {100 * r.success_rate:.1f}% | "
                 f"{100 * r.handled_alone_correct:.1f}% | ${r.all_in_usd_per_chat_at_100000:.2f} | ${r.all_in_usd_per_successful_chat_at_100000:.2f} | "
                 f"${r.all_in_usd_per_chat_without_missed_handoff_cost:.2f} |")
    names = {"status_quo": "People only (today)", **{k: v[1] for k, v in OPTIONS.items()}}
    for v in sorted(scen.chats_per_month.unique()):
        L += ["", f"## {v:,} chats a month (USD per month)", "",
              "| Option | Model calls | People (handoffs, rework, review) | Mistakes | Servers, monitoring, engineering, build | Total | Saving vs today |",
              "|---|---|---|---|---|---|---|"]
        for _, r in scen[scen.chats_per_month == v].iterrows():
            people = r.people_handoffs + r.get("people_rework", 0) + r.get("people_review", 0)
            mist = sum(r.get(c, 0) for c in ["mistakes_wrong_commitment", "mistakes_invented_fact", "mistakes_missed_handoff", "mistakes_expensive_promise"])
            fixed = sum(r.get(c, 0) for c in ["app_servers", "monitoring", "evaluation_runs", "engineering", "build_paid_back", "finetuned_router_server"])
            L.append(f"| {names[r.option]} | {_money(r.get('model_calls', 0))} | {_money(people)} | {_money(mist)} | {_money(fixed)} | "
                     f"{_money(r.total)} | {_money(r.saving_vs_status_quo)} ({r.saving_pct:+.1f}%) |")
    L += ["", "## Cost of one mistake (USD)", "", "| Mistake | Cost |", "|---|---|"]
    L += [f"| {r.mistake} | {_money(r.usd_per_event)} |" for _, r in mistakes.iterrows()]
    be = summary["breakeven"]
    L += ["", "## Break-even points (recommended agent)", "",
          "| Volume (chats a month) | Agent saving | Expensive-promise rate that wipes out the saving | Small wrong-commitment rate that wipes it out | Containment needed |",
          "|---|---|---|---|---|"]
    for v, s in summary["saving_at"].items():
        pct = lambda x, nd: "n/a (loses even with no mistakes)" if x is None else f"{100 * x:.{nd}f}%"  # noqa: E731
        L.append(f"| {int(v):,} | {_money(s[RECOMMENDED])} | {pct(be['expensive_promise_rate'][v], 3)} | "
                 f"{pct(be['small_wrong_commitment_rate'][v], 1)} | {pct(be['containment'][v], 1)} |")
    L += ["", "## Larger or smaller model, part by part", "",
          "| Part | Extra cost per conversation (larger) | Mistake it guards against | Cost of that mistake | One avoided mistake pays for | Measured difference | Decision |",
          "|---|---|---|---|---|---|---|"]
    for _, r in big.iterrows():
        L.append(f"| {r.part} | ${r.extra_usd_per_conversation:.4f} | {r.mistake_guarded} | {_money(r.mistake_cost_usd)} | "
                 f"{r.one_avoided_mistake_pays_for_conversations:,} conversations | {r.measured_quality_difference} | {r.decision} |")
    vols = [summary["northstar_volume"], 100_000]
    L += ["", "## Sensitivity: saving per month, one assumption at a time (recommended agent)", "",
          f"| Assumption | Pessimistic / optimistic value | {vols[0]:,} chats: pessimistic | optimistic | 100,000 chats: pessimistic | optimistic |",
          "|---|---|---|---|---|---|"]
    for _, r in sens.iterrows():
        L.append(f"| {r.assumption} | {r.pessimistic:.4g} / {r.optimistic:.4g} | {_money(r[f'saving_pessimistic_{vols[0]}'])} | "
                 f"{_money(r[f'saving_optimistic_{vols[0]}'])} | {_money(r['saving_pessimistic_100000'])} | {_money(r['saving_optimistic_100000'])} |")
    f, base = summary.get("fresh_set_check"), summary["measured"][RECOMMENDED]
    if f:
        test_ho = summary["handoff_evidence"]["by_source"]["test chats"]

        def cell(x, pct):
            return f"{_money(x)} ({pct:+.1f}%)"

        L += ["", "## Fresh held-out set beside the base case (recommended agent, USD per month)", "",
              f"| Rates used | Finished alone and correct | Needed a person and got one | Saving at {vols[0]:,} chats | Saving at 100,000 chats |",
              "|---|---|---|---|---|",
              f"| {base['n']} test chats (base case of the model) | {100 * base['handled_alone_correct']:.1f}% ({base['handled_alone_correct_k']} of {base['n']}) | "
              f"{test_ho['needed_a_person'] - test_ho['missed']} of {test_ho['needed_a_person']} | "
              + " | ".join(cell(summary["saving_at"][str(v)][RECOMMENDED], summary["saving_pct_at"][str(v)][RECOMMENDED]) for v in vols) + " |"]
        for tag, label in (("missed_handoffs_not_priced", "missed handoffs not priced"),
                           ("missed_handoffs_priced", f"missed handoffs at {_money(f['missed_handoff_usd'])} each")):
            L.append(f"| {f['chats']} fresh chats, {label} | {100 * f['finished_alone_correct_rate']:.1f}% ({f['finished_alone_correct']} of {f['chats']}) | "
                     f"{f['handoffs_made']} of {f['handoffs_needed']} | "
                     + " | ".join(cell(f["saving_at"][str(v)][tag], f["saving_pct_at"][str(v)][tag]) for v in vols) + " |")
        fp, bp = f["pilot"], summary["pilot"]
        pilot_line = (f"Pilot month ({fp['chats_per_month']:,} chats, a person approves billing and warranty replies): "
                      f"{_money(bp['saving_usd_per_month'])} at the test-chat rates; "
                      f"{_money(fp['saving_usd_per_month']['missed_handoffs_not_priced'])} at the fresh-chat rates with missed handoffs not priced "
                      f"({100 * fp['money_desk_share']:.1f}% of fresh chats go to a money desk, {100 * bp['money_desk_share']:.1f}% of test chats); "
                      f"{_money(fp['saving_usd_per_month']['missed_handoffs_priced'])} with them priced.")
        L += ["", pilot_line]
    g = summary.get("grader_vs_people")
    if g:
        people = " and ".join(f"{100 * x:.1f}%" for x in g["main_agent_success_by_people"])
        row = (f"| {g['replies_checked']} | {' and '.join(f'{k:.2f}' for k in g['kappa_overall_success'])} | {people} | "
               f"{100 * g['main_agent_success_by_grader']:.1f}% |")
        L += ["", "## Model grader against people (recommended agent, test replies)", "",
              "| Replies checked by two people | Agreement on overall success (Cohen's kappa) | Success by the two people | Success by the grader |",
              "|---|---|---|---|", row]
    (OUT / "tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def chart(a, mes, ev, hosting, be) -> None:
    """Monthly cost per chat against volume: today vs the three router options."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker  # noqa: F401
    except ImportError:
        # The chart only draws numbers the tables above already hold. Without matplotlib the cost
        # model must still run, so every number in the memo stays reproducible.
        print("matplotlib not installed: skipped the chart (pip install -r requirements.txt adds it)")
        return

    vols = np.unique(np.round(np.geomspace(500, 1_500_000, 200))).astype(int)
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=150)
    ax.plot(vols, [status_quo(v, a)["total"] / v for v in vols], color="#3f3f46", lw=2, label="People only (today)")
    # Large and fine-tuned routers each missed one handoff in 40 chats; priced at $500 that alone puts them
    # near $15 a chat, off this chart. They are drawn WITHOUT that cost, to show they lose even then.
    style = {"small_prompted": ("#2563eb", "-", False, OPTIONS["small_prompted"][1]),
             "small_prompted_pilot": ("#0d9488", "-.", False, "Recommended agent in the pilot (person approves money replies)"),
             "large_prompted": ("#d97706", "--", True, "Large prompted router (missed handoff not priced)"),
             "finetuned": ("#7c3aed", ":", True, "Fine-tuned router (missed handoff not priced)")}
    for key, (col, ls, drop_miss, label) in style.items():
        ys = []
        for v in vols:
            c = agent_month(v, a, mes[key], key, ev["measured"], hosting)
            ys.append((c["total"] - (c["mistakes_missed_handoff"] if drop_miss else 0)) / v)
        ax.plot(vols, ys, color=col, ls=ls, lw=2, label=label)
    bv = be["volume"][RECOMMENDED]
    if bv:
        ax.axvline(bv, color="#2563eb", lw=0.8, alpha=0.5)
        ax.annotate(f"break-even\n{bv:,} chats", (bv, 0.9), fontsize=8, color="#2563eb", ha="left", xytext=(4, 0), textcoords="offset points")
    for v in a["volumes"]:
        ax.axvline(v, color="#a1a1aa", lw=0.5, ls=":")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_ylim(0, 4)
    ax.set_xlabel("Chats per month (log scale)")
    ax.set_ylabel("All-in cost per chat (USD)")
    ax.set_title("All-in cost per chat, mistakes included", fontsize=10, loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=7.5, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT / "cost_per_chat_vs_volume.png")
    plt.close(fig)

    # The same curves once more, wide and short, for report page 7: at page width the chart above
    # would be half a page tall, and shrunk to fit its labels are too small to read.
    short = {"small_prompted": "Recommended agent", "small_prompted_pilot": "Agent in the pilot (approvals)",
             "large_prompted": "Sonnet router*", "finetuned": "Fine-tuned router*"}
    fig, ax = plt.subplots(figsize=(6.5, 2.2), dpi=200)
    ax.plot(vols, [status_quo(v, a)["total"] / v for v in vols], color="#3f3f46", lw=1.8, label="People only (today)")
    for key, (col, ls, drop_miss, _) in style.items():
        ys = []
        for v in vols:
            c = agent_month(v, a, mes[key], key, ev["measured"], hosting)
            ys.append((c["total"] - (c["mistakes_missed_handoff"] if drop_miss else 0)) / v)
        ax.plot(vols, ys, color=col, ls=ls, lw=1.8, label=short[key])
    if bv:
        ax.axvline(bv, color="#2563eb", lw=0.8, alpha=0.5)
        ax.annotate(f"break-even {bv:,} chats", (bv, 1.62), fontsize=7.5, color="#2563eb", ha="left", xytext=(3, 0), textcoords="offset points")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_xlim(700, 1_500_000)
    ax.set_ylim(1.5, 4)                      # the axis starts at $1.50, and says so: below it there is nothing to see
    ax.set_xlabel("Chats per month (log scale)   * its missed handoff not priced", fontsize=8)
    ax.set_ylabel("All-in cost per chat\n(USD, axis from 1.50)", fontsize=8)
    ax.tick_params(labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=7.5, loc="upper right", ncol=2, columnspacing=1.2, handlelength=2.2)
    fig.tight_layout(pad=0.4)
    fig.savefig(OUT / "cost_per_chat_vs_volume_page7.png")
    plt.close(fig)


def main() -> None:
    s = build()
    print(json.dumps({k: s[k] for k in ("status_quo_usd_per_chat", "saving_at", "saving_pct_at", "monte_carlo")}, indent=1))
    print(json.dumps(s["breakeven"], indent=1))
    print(f"\nTables: {OUT / 'tables.md'}")
