"""Three-router comparison on the 40 test chats: fine-tuned vs small prompted vs large prompted.

Every number comes from the row-level results written by the same evaluation
(`python -m northstar.agent.router --split test --model ...`), and every metric
is computed by the same function for all three routers. Nothing is typed by hand.

    # after the three test runs, copy their results here and build the tables:
    python -m northstar.finetune.compare --collect
    # rebuild the tables from the copies kept in the repo (no GPU, no key):
    python -m northstar.finetune.compare

Writes to src/northstar/finetune/results/:
    comparison_table.csv       headline metrics, one row per router
    comparison_per_class.csv   accuracy for each of the 10 request types
    comparison_by_slice.csv    accuracy by language, difficulty and adversarial type
    comparison_stats.json      95% confidence intervals and paired tests (40 chats is small)

The table also shows the router inside the agent: the pipeline sends any chat to a person
when the router's confidence is below agent.router_confidence_floor (settings), so a
low-confidence mistake reaches a person instead of the wrong specialist.
"""
from __future__ import annotations

import argparse
import json
import shutil
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from northstar.config import path, settings
from northstar.contracts import RequestType

HERE = Path(__file__).parent / "results"
RUNS = HERE / "router_test"          # copies of the three test runs, kept in the repo
ROUTERS = {  # label: file prefix written by northstar.agent.router
    "Fine-tuned (XLM-R)": "router_finetuned-",
    "Small prompted (Haiku)": "router_claude-haiku",
    "Large prompted (Sonnet)": "router_claude-sonnet",
}
LABELS = [t.value for t in RequestType]


def find(folder: Path, prefix: str) -> Path:
    hits = sorted(folder.glob(f"{prefix}*_test.csv"))
    if not hits:
        raise FileNotFoundError(f"No test results starting with {prefix} in {folder}. "
                                f"Run: python -m northstar.agent.router --split test --model ...")
    return hits[-1]


def collect() -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    for prefix in ROUTERS.values():
        csv = find(path("results_dir"), prefix)
        for f in (csv, csv.with_suffix(".json")):
            shutil.copy(f, RUNS / f.name)
            print("copied", f.name)


def headline(df: pd.DataFrame, js: dict) -> dict:
    esc, flagged = df[df.gold_escalation], df[df.pred_escalation]
    by_lang = df.groupby("gold_language").type_correct.mean()
    floor = settings()["agent"].get("router_confidence_floor", 0.55)
    to_person = df.pred_escalation | (pd.to_numeric(df.confidence, errors="coerce") < floor)   # same rule as pipeline.py
    return {
        "type_accuracy": df.type_correct.mean(),
        "macro_f1": f1_score(df.gold_type, df.pred_type, labels=LABELS, average="macro", zero_division=0),
        "escalation_recall": esc.pred_escalation.mean(),
        "escalation_precision": flagged.gold_escalation.mean() if len(flagged) else np.nan,
        "escalation_accuracy": (df.gold_escalation == df.pred_escalation).mean(),
        "missed_escalations": int((df.gold_escalation & ~df.pred_escalation).sum()),
        "language_accuracy": (df.gold_language == df.pred_language).mean(),
        "en_type_accuracy": by_lang.get("en", np.nan),
        "fr_type_accuracy": by_lang.get("fr", np.nan),
        "latency_ms_median": df.latency_ms.median(),
        "latency_ms_p90": df.latency_ms.quantile(0.9),
        "agent_wrong_type_reaching_specialist": int((~df.type_correct & ~to_person).sum()),
        "agent_missed_escalations": int((df.gold_escalation & ~to_person).sum()),
        "agent_handoffs": int(to_person.sum()),
        "agent_unneeded_handoffs": int((to_person & ~df.gold_escalation).sum()),
        "cost_usd_per_chat": df.cost_usd.mean(),
        "cost_usd_per_1000_chats": df.cost_usd.mean() * 1000,
        "n": len(df),
    }


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 3), round(c + h, 3)


def mcnemar_exact(a_right: pd.Series, b_right: pd.Series) -> dict:
    """Paired test on the same chats: only the chats where exactly one router is right count."""
    b = int((a_right & ~b_right).sum())
    c = int((~a_right & b_right).sum())
    n = b + c
    p = 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)
    return {"only_first_right": b, "only_second_right": c, "p_value": round(p, 3)}


def build() -> pd.DataFrame:
    frames = {}
    for label, prefix in ROUTERS.items():
        csv = find(RUNS, prefix)
        df = pd.read_csv(csv, keep_default_na=False)
        for col in ("gold_escalation", "pred_escalation", "type_correct"):
            df[col] = df[col].astype(str).str.lower().eq("true")
        frames[label] = (df.sort_values("id").reset_index(drop=True), json.loads(csv.with_suffix(".json").read_text()))
    ids = [tuple(f[0].id) for f in frames.values()]
    assert all(i == ids[0] for i in ids), "the three routers were not scored on the same chats"

    table = pd.DataFrame([{"router": k, "model": js["model"], **headline(df, js)} for k, (df, js) in frames.items()])
    table.round(4).assign(cost_usd_per_chat=table.cost_usd_per_chat.round(6)).to_csv(HERE / "comparison_table.csv", index=False)

    per_class = pd.DataFrame({k: df.groupby("gold_type").type_correct.mean() for k, (df, _) in frames.items()})
    per_class.insert(0, "n", frames[next(iter(frames))][0].gold_type.value_counts())
    per_class.round(3).to_csv(HERE / "comparison_per_class.csv", index_label="request_type")

    slices = []
    for col in ("gold_language", "difficulty", "adversarial_type"):
        for k, (df, _) in frames.items():
            for val, g in df.groupby(col):
                slices.append(dict(slice=col, value=val or "none", router=k, n=len(g), type_accuracy=g.type_correct.mean(),
                                   escalation_recall=g[g.gold_escalation].pred_escalation.mean() if g.gold_escalation.any() else np.nan))
    pd.DataFrame(slices).round(3).to_csv(HERE / "comparison_by_slice.csv", index=False)

    labels = list(frames)
    ft = frames[labels[0]][0]
    stats = {"type_accuracy_95ci": {k: wilson(int(df.type_correct.sum()), len(df)) for k, (df, _) in frames.items()},
             "paired_tests_type_accuracy": {f"{labels[0]} vs {k}": mcnemar_exact(ft.type_correct, frames[k][0].type_correct)
                                            for k in labels[1:]},
             "note": "40 test chats: a 10-point gap is 4 chats. Read the intervals before reading the gap."}
    (HERE / "comparison_stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    return table


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collect", action="store_true", help="copy the latest test results from outputs/results first")
    a = ap.parse_args()
    if a.collect:
        collect()
    t = build()
    with pd.option_context("display.width", 200):
        print(t.round(3).assign(cost_usd_per_chat=t.cost_usd_per_chat.round(6)).T.to_string(header=False))
    print(json.dumps(json.loads((HERE / "comparison_stats.json").read_text()), indent=1))


if __name__ == "__main__":
    main()
