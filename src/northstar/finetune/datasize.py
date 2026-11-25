"""How much training data would the fine-tuned router need to match Haiku? (Phase 5, task 13)

Reads the learning-curve runs (`train_router.py datasize`: 25%, 50%, 75% and 100% of the
130 training chats, 3 seeds each, scored on the 30 validation chats). Fits a straight line
of accuracy against the log of the number of chats, which gives the gain each time the data
doubles. Validation chose the model's settings, so its validation score is optimistic; the
honest gap is the one already measured on the test chats. The estimate is how much more data
would close that test gap if the gain per doubling held. Haiku's validation number is replayed
from the recordings, so no key is needed.

    python -m northstar.finetune.datasize

No new test scoring: the test gap is read from results/comparison_table.csv.

Writes results/datasize_summary.json and results/datasize_curve.png.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent / "results"
N_TYPES = 10


def haiku_validation_accuracy() -> float:
    from northstar.agent.router import evaluate      # replays the recorded calls: free, no key
    _, summary = evaluate("validation", "small")
    return float(summary["type_accuracy"])


def fit(x_chats: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    b, a = np.polyfit(np.log(x_chats), y, 1)       # y = a + b * ln(chats)
    return float(a), float(b)


def test_gap() -> float:
    """Haiku minus fine-tuned request-type accuracy on the 40 test chats (already scored, read from file)."""
    t = pd.read_csv(HERE / "comparison_table.csv").set_index("router")
    return float(t.loc["Small prompted (Haiku)", "type_accuracy"] - t.loc["Fine-tuned (XLM-R)", "type_accuracy"])


def chats_to_close(have: int, gap: float, gain_per_doubling: float) -> float:
    """If accuracy kept rising by the same amount each time the data doubles."""
    return float(have * 2 ** (gap / gain_per_doubling)) if gain_per_doubling > 0 else float("inf")


def build(haiku_val: float | None = None, gap: float | None = None) -> dict:
    runs = pd.read_csv(HERE / "datasize_runs.csv")
    haiku_val = haiku_validation_accuracy() if haiku_val is None else haiku_val
    gap = test_gap() if gap is None else gap
    curve = runs.groupby("train_chats").agg(acc_mean=("val_type_accuracy", "mean"), acc_std=("val_type_accuracy", "std"),
                                            f1_mean=("val_macro_f1", "mean"), runs=("seed", "count")).reset_index()
    a, b = fit(runs.train_chats.values.astype(float), runs.val_type_accuracy.values)
    gain = b * np.log(2)
    have = int(runs.train_chats.max())
    need = chats_to_close(have, gap, gain)

    # How sure is the growth rate? Refit on resampled runs (same sizes, seeds drawn with replacement).
    rng = np.random.default_rng(894)
    groups = [g.val_type_accuracy.values for _, g in runs.groupby("train_chats")]
    sizes = [float(n) for n, _ in runs.groupby("train_chats")]
    boot = []
    for _ in range(2000):
        xs = np.concatenate([[n] * len(g) for n, g in zip(sizes, groups)])
        ys = np.concatenate([rng.choice(g, size=len(g), replace=True) for g in groups])
        _, b_ = fit(xs, ys)
        boot.append(chats_to_close(have, gap, b_ * np.log(2)))
    lo, hi = np.percentile(boot, [10, 90])

    summary = {
        "curve_validation": curve.round(3).to_dict("records"),
        "gain_per_doubling_points": round(100 * gain, 1),
        "levelling_off": bool(curve.acc_mean.diff().iloc[-1] < 0.25 * curve.acc_mean.diff().iloc[1]),
        "validation": {"finetuned_at_full_data": round(float(curve.acc_mean.iloc[-1]), 3), "haiku": round(haiku_val, 3),
                       "note": "validation chose the fine-tuned settings, so its validation score is optimistic"},
        "test_gap_points": round(100 * gap, 1),
        "chats_to_close_test_gap_if_trend_holds": int(round(need, -1)),
        "per_request_type": int(round(need / N_TYPES)),
        "range_80pct": [int(round(lo, -1)), int(round(hi, -1))],
        "fit": {"formula": "accuracy = a + b * ln(training chats)", "a": round(a, 4), "b": round(b, 4)},
        "caveat": "Learning curves flatten as they approach their ceiling, so this is a lower bound: "
                  "a few hundred chats is a safer planning figure. Four sizes, 30 validation chats.",
    }
    (HERE / "datasize_summary.json").write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    plot(runs, curve, a, b, haiku_val)
    return summary


def plot(runs, curve, a, b, target) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed: skipped the chart")
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(runs.train_chats, runs.val_type_accuracy, color="#1f77b4", alpha=0.35, label="one training run")
    ax.plot(curve.train_chats, curve.acc_mean, "o-", color="#1f77b4", lw=2, label="mean of 3 seeds")
    xs = np.geomspace(curve.train_chats.min(), curve.train_chats.max(), 100)
    ax.plot(xs, a + b * np.log(xs), "--", color="#7f7f7f", label="trend (fit on log of data size)")
    ax.axhline(target, color="#d62728", lw=1.2, label=f"Haiku on validation ({target:.0%})")
    ax.set_xscale("log")
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_xticks(list(curve.train_chats), [str(int(n)) for n in curve.train_chats])
    ax.set_xlabel("training chats (log scale)")
    ax.set_ylabel("validation request-type accuracy")
    ax.set_title("Fine-tuned router: accuracy vs training data")
    ax.legend(fontsize=8, loc="lower right")
    plt.tight_layout()
    plt.savefig(HERE / "datasize_curve.png", dpi=150)


def main() -> None:
    print(json.dumps(build(), indent=1, default=float))


if __name__ == "__main__":
    main()
