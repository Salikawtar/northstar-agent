"""How much training data would the fine-tuned router need to match Haiku? (Phase 5, task 13)

Reads the learning-curve runs (`train_router.py datasize`: 25%, 50%, 75% and 100% of the
130 training chats, 3 seeds each, scored on the 30 validation chats). Fits a straight line
of accuracy against the log of the number of chats (accuracy usually grows by about the same
amount each time the data doubles), and asks where that line reaches Haiku's validation
accuracy. Haiku's number is replayed from the recordings, so no key is needed.

    python -m northstar.finetune.datasize

Everything here uses validation chats only: the test chats stay untouched.

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


def chats_to_reach(target: float, a: float, b: float) -> float:
    return float(np.exp((target - a) / b)) if b > 0 else float("inf")


def build(target: float | None = None) -> dict:
    runs = pd.read_csv(HERE / "datasize_runs.csv")
    target = haiku_validation_accuracy() if target is None else target
    curve = runs.groupby("train_chats").agg(acc_mean=("val_type_accuracy", "mean"), acc_std=("val_type_accuracy", "std"),
                                            f1_mean=("val_macro_f1", "mean"), runs=("seed", "count")).reset_index()
    a, b = fit(runs.train_chats.values.astype(float), runs.val_type_accuracy.values)
    need = chats_to_reach(target, a, b)

    # How sure is that? Refit on resampled runs (same sizes, seeds drawn with replacement).
    rng = np.random.default_rng(894)
    boot = []
    groups = [g.val_type_accuracy.values for _, g in runs.groupby("train_chats")]
    sizes = [float(n) for n, _ in runs.groupby("train_chats")]
    for _ in range(2000):
        xs = np.concatenate([[n] * len(g) for n, g in zip(sizes, groups)])
        ys = np.concatenate([rng.choice(g, size=len(g), replace=True) for g in groups])
        a_, b_ = fit(xs, ys)
        boot.append(chats_to_reach(target, a_, b_))
    lo, hi = np.percentile(boot, [10, 90])

    have = int(runs.train_chats.max())
    summary = {
        "haiku_validation_type_accuracy": round(target, 3),
        "finetuned_validation_type_accuracy_at_full_data": round(float(curve.acc_mean.iloc[-1]), 3),
        "fit": {"formula": "accuracy = a + b * ln(training chats)", "a": round(a, 4), "b": round(b, 4),
                "gain_per_doubling_points": round(100 * b * np.log(2), 1)},
        "training_chats_to_match_haiku": int(round(need, -1)) if np.isfinite(need) else None,
        "per_request_type": int(round(need / N_TYPES)) if np.isfinite(need) else None,
        "times_current_data": round(need / have, 1) if np.isfinite(need) else None,
        "range_80pct": [int(round(lo, -1)), int(round(hi, -1))] if np.isfinite(hi) else [int(round(lo, -1)), None],
        "curve": curve.round(3).to_dict("records"),
        "caveat": "Four sizes on 30 validation chats: the extrapolation is a rough order of magnitude, "
                  "and accuracy may level off before reaching Haiku.",
    }
    (HERE / "datasize_summary.json").write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    plot(runs, curve, a, b, target, need)
    return summary


def plot(runs, curve, a, b, target, need) -> None:
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
    x_end = max(curve.train_chats.max() * 1.2, min(need * 1.3, curve.train_chats.max() * 20)) if np.isfinite(need) else 400
    xs = np.geomspace(curve.train_chats.min(), x_end, 100)
    ax.plot(xs, a + b * np.log(xs), "--", color="#7f7f7f", label="trend (fit on log of data size)")
    ax.axhline(target, color="#d62728", lw=1.2, label=f"Haiku on validation ({target:.0%})")
    ax.set_xscale("log")
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
