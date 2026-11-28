"""Scoring helpers, written once so every method is scored by exactly the same code.

Plain numpy / scikit-learn / scipy only (no torch), so the analysis can run on any laptop.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import binomtest
from sklearn.metrics import accuracy_score, f1_score, fbeta_score, precision_score, recall_score


def type_scores(y_true, logits) -> dict:
    """Request type: accuracy and macro-F1 (average of the per-type F1, so every type counts equally)."""
    pred = np.asarray(logits).argmax(-1)
    return dict(accuracy=float(accuracy_score(y_true, pred)),
                macro_f1=float(f1_score(y_true, pred, average="macro", labels=np.arange(np.asarray(logits).shape[-1]),
                                        zero_division=0)))


def escalation_scores(y_true, logits, threshold: float = 0.0) -> dict:
    """Escalation yes/no. `logits` > threshold means "escalate" (0.0 is the same as probability 0.5).
    F2 counts a missed escalation twice as bad as a false alarm."""
    pred = (np.asarray(logits) > threshold).astype(int)
    y = np.asarray(y_true).astype(int)
    return dict(recall=float(recall_score(y, pred, zero_division=0)),
                precision=float(precision_score(y, pred, zero_division=0)),
                f2=float(fbeta_score(y, pred, beta=2, zero_division=0)),
                accuracy=float(accuracy_score(y, pred)),
                missed=int(((y == 1) & (pred == 0)).sum()),
                false_alarms=int(((y == 0) & (pred == 1)).sum()))


def per_class_recall(y_true, pred, n_classes: int) -> np.ndarray:
    """For each class: of the chats that truly belong to it, the share we got right (nan if none exist)."""
    y, p = np.asarray(y_true), np.asarray(pred)
    return np.array([(p[y == c] == c).mean() if (y == c).any() else np.nan for c in range(n_classes)])


def cluster_bootstrap(stat_fn, groups, n_boot: int = 2000, seed: int = 0):
    """95% interval for a statistic by resampling CUSTOMERS (groups), not single chats, because one
    customer's chats are not independent. stat_fn(index_array) must return a number."""
    groups = np.asarray(groups)
    uniq = np.unique(groups)
    members = {g: np.where(groups == g)[0] for g in uniq}
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)          # draw customers with replacement
        stats[b] = stat_fn(np.concatenate([members[g] for g in pick]))
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def mcnemar_exact(correct_a, correct_b) -> dict:
    """Do two methods differ on the same chats? Only the chats where exactly one of them is right matter.
    Exact two-sided test: if there were no real difference, those chats would split 50/50."""
    a, b = np.asarray(correct_a).astype(bool), np.asarray(correct_b).astype(bool)
    only_a, only_b = int((a & ~b).sum()), int((~a & b).sum())
    n = only_a + only_b
    p = 1.0 if n == 0 else float(binomtest(only_a, n, 0.5).pvalue)
    return dict(only_a_right=only_a, only_b_right=only_b, p_value=p)
