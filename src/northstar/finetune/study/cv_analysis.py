"""Analysis of saved cross-validation runs. CPU only (numpy, pandas, scikit-learn): runs on any laptop.

The training step (train_cv.py) saves, for every run, the raw scores of its held-out fold at every epoch.
Here we put the five folds of one seed back together, so that every one of the 160 chats has a score
from a model that never saw it ("out-of-fold" score), and then measure those scores.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from northstar.finetune.study import protocol as P
from northstar.finetune.study.metrics import escalation_scores, type_scores


def load_variant(run_dir, variant: str, rep: int = 0) -> list:
    """All saved runs of one input variant (each run is a dict of arrays)."""
    files = sorted(Path(run_dir, variant).glob(f"rep{rep}_seed*_fold*.npz"))
    if not files:
        raise FileNotFoundError(f"no saved runs in {Path(run_dir, variant)}")
    runs = []
    for f in files:
        z = np.load(f, allow_pickle=False)
        runs.append({k: z[k] for k in z.files})
    return runs


def assemble(runs: list, pool: pd.DataFrame, heads=("type", "escalation")) -> dict:
    """{seed: {head: scores of shape [epochs, 160, ...]}} with chats in the pool's order.
    Raises if any chat is missing (an incomplete cross-validation must not be analysed by accident)."""
    position = {cid: i for i, cid in enumerate(pool["id"])}
    result = {}
    for seed in sorted({int(r["seed"]) for r in runs}):
        mine = [r for r in runs if int(r["seed"]) == seed]
        epochs = mine[0]["train_loss"].shape[0]
        arrays = {}
        for h in heads:
            rest = mine[0][f"logits_{h}"].shape[2:]
            arrays[h] = np.full((epochs, len(pool)) + rest, np.nan, dtype=np.float32)
        for r in mine:
            rows = [position[str(c)] for c in r["ids"]]
            for h in heads:
                arrays[h][:, rows] = r[f"logits_{h}"]
        for h in heads:
            if np.isnan(arrays[h]).any():
                folds = sorted(int(r["fold"]) for r in mine)
                raise ValueError(f"seed {seed}: some chats have no score (folds present: {folds})")
        result[seed] = arrays
    return result


def loss_curves(runs: list) -> pd.DataFrame:
    """Training and held-out loss per epoch, one row per (seed, fold, epoch)."""
    rows = []
    for r in runs:
        for e, (tl, vl) in enumerate(zip(r["train_loss"], r["val_loss"]), start=1):
            rows.append(dict(seed=int(r["seed"]), fold=int(r["fold"]), epoch=e, train_loss=float(tl), val_loss=float(vl)))
    return pd.DataFrame(rows)


def epoch_curves(oof: dict, pool: pd.DataFrame) -> pd.DataFrame:
    """Out-of-fold scores of the type and escalation questions, per seed and epoch."""
    y_type, y_esc = pool["type_label"].values, pool["escalation_label"].values
    rows = []
    for seed, arr in oof.items():
        for e in range(arr["type"].shape[0]):
            t = type_scores(y_type, arr["type"][e])
            s = escalation_scores(y_esc, arr["escalation"][e])
            row = dict(seed=seed, epoch=e + 1, type_accuracy=t["accuracy"], type_macro_f1=t["macro_f1"],
                       esc_recall=s["recall"], esc_precision=s["precision"], esc_f2=s["f2"],
                       esc_accuracy=s["accuracy"])
            if "language" in arr:       # only for runs that also had a language head
                row["language_accuracy"] = float((arr["language"][e].argmax(-1) == pool["language_label"].values).mean())
            if "attack" in arr:         # only for runs that also had an attack head
                a = escalation_scores(pool["attack_label"].values, arr["attack"][e])
                row.update(attack_recall=a["recall"], attack_precision=a["precision"], attack_f2=a["f2"])
            rows.append(row)
    return pd.DataFrame(rows)


def pick_epoch(curves: pd.DataFrame, metric: str = "type_macro_f1", window: int = 3) -> tuple:
    """Choose ONE epoch count for all runs: average the metric over seeds, smooth it over `window`
    neighbouring epochs (single epochs are noisy), take the best. Returns (epoch, smoothed curve)."""
    mean_curve = curves.groupby("epoch")[metric].mean()
    smooth = mean_curve.rolling(window, center=True, min_periods=1).mean()
    return int(smooth.idxmax()), smooth


def summary_at_epoch(oof: dict, pool: pd.DataFrame, epoch: int, threshold: float = 0.0) -> dict:
    """Scores at one epoch: per seed, their mean and spread, and the average-of-seeds ("ensemble") score."""
    y_type, y_esc = pool["type_label"].values, pool["escalation_label"].values
    per_seed = []
    for seed, arr in oof.items():
        t = type_scores(y_type, arr["type"][epoch - 1])
        s = escalation_scores(y_esc, arr["escalation"][epoch - 1], threshold)
        row = dict(seed=seed, type_accuracy=t["accuracy"], type_macro_f1=t["macro_f1"],
                   esc_recall=s["recall"], esc_precision=s["precision"], esc_f2=s["f2"],
                   esc_accuracy=s["accuracy"], esc_missed=s["missed"], esc_false_alarms=s["false_alarms"])
        if "language" in arr:
            row["language_accuracy"] = float((arr["language"][epoch - 1].argmax(-1) == pool["language_label"].values).mean())
        if "attack" in arr:
            a = escalation_scores(pool["attack_label"].values, arr["attack"][epoch - 1])
            row.update(attack_recall=a["recall"], attack_precision=a["precision"], attack_f2=a["f2"],
                       attack_missed=a["missed"], attack_false_alarms=a["false_alarms"])
        per_seed.append(row)
    per_seed = pd.DataFrame(per_seed)
    avg_type = np.mean([a["type"][epoch - 1] for a in oof.values()], axis=0)       # average the scores of all seeds
    avg_esc = np.mean([a["escalation"][epoch - 1] for a in oof.values()], axis=0)
    t, s = type_scores(y_type, avg_type), escalation_scores(y_esc, avg_esc, threshold)
    out = dict(per_seed=per_seed, ensemble_type=t, ensemble_escalation=s,
               ensemble_type_logits=avg_type, ensemble_escalation_logits=avg_esc)
    if all("attack" in a for a in oof.values()):
        out["ensemble_attack_logits"] = np.mean([a["attack"][epoch - 1] for a in oof.values()], axis=0)
        out["ensemble_attack"] = escalation_scores(pool["attack_label"].values, out["ensemble_attack_logits"])
    return out
