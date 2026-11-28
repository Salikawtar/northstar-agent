"""Make the cross-validation folds once, save them, and never redraw them.

Why a saved file: fold-splitting routines can give different folds on different library
versions (the team saw this with scikit-learn), so every machine (laptop, Kaggle) must read
the same saved assignment instead of drawing its own.

- Pool: the 160 train + validation chats. The 40 test chats are never in a fold.
- Groups: customer_id. All chats of one customer sit in the same fold. (There are only 79
  customers in the pool, so random grouped splits come out lopsided: one fold can hold 4
  French chats and another 15.)
- Balance: customers are assigned to folds by a small simulated-annealing search that keeps
  every fold close to the overall mix of request types, escalation rate, adversarial rate,
  French share and size, and avoids any fold missing a request type. It uses labels only,
  never model results, and needs only numpy, so the result does not depend on scikit-learn.
- Three repeats (rep0, rep1, rep2) are saved. rep0 is the default; the others are for a
  repeated-CV check later.

Run:  PYTHONPATH=src python -m northstar.finetune.study.make_folds
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd

from northstar.finetune.study import protocol as P

N_REPS = 3
RESTARTS = 4
ITERS = 60_000
K = P.N_FOLDS
N_TYPES = len(P.REQUEST_TYPES)
# columns of the per-customer count matrix: 10 types, escalation, adversarial, French, size
DIMS = N_TYPES + 4
WEIGHTS = np.array([1.0] * N_TYPES + [2.0, 2.0, 2.0, 3.0])


def customer_matrix(frame: pd.DataFrame) -> tuple[np.ndarray, list]:
    rows, ids = [], []
    for cid, g in frame.groupby("customer_id", sort=True):
        tc = g["request_type"].value_counts().reindex(P.REQUEST_TYPES, fill_value=0).values.astype(float)
        rows.append(np.concatenate([tc, [g["escalation_label"].sum(), g["adversarial"].sum(),
                                         (g["language"] == "fr").sum(), len(g)]]))
        ids.append(cid)
    return np.array(rows), ids


def optimise(X: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, float]:
    """Assign each customer (row of X) to one of K folds so that fold mixes are even."""
    n = len(X)
    target = X.sum(0) / K
    scale = np.maximum(target, 1.0)

    def row_cost(r: np.ndarray) -> float:
        # relative deviation per dimension, plus a heavy penalty for a request type missing from the fold
        return float((WEIGHTS * np.abs(r - target) / scale).sum() + 5.0 * (r[:N_TYPES] == 0).sum())

    best_assign, best_total = None, float("inf")
    for _ in range(RESTARTS):
        assign = rng.integers(0, K, n)
        F = np.zeros((K, DIMS))
        for i in range(n):
            F[assign[i]] += X[i]
        costs = np.array([row_cost(F[k]) for k in range(K)])
        t0, t1 = 0.5, 0.005
        for it in range(ITERS):
            temp = t0 * (t1 / t0) ** (it / ITERS)
            if rng.random() < 0.5:                      # move one customer to another fold
                i = int(rng.integers(n)); a = int(assign[i])
                b = int(rng.integers(K - 1)); b = b if b < a else b + 1
                Fa, Fb = F[a] - X[i], F[b] + X[i]
                na, nb = row_cost(Fa), row_cost(Fb)
                delta = na + nb - costs[a] - costs[b]
                if delta < 0 or rng.random() < np.exp(-delta / temp):
                    F[a], F[b], costs[a], costs[b], assign[i] = Fa, Fb, na, nb, b
            else:                                       # swap two customers between folds
                i, j = (int(v) for v in rng.integers(n, size=2))
                a, b = int(assign[i]), int(assign[j])
                if a == b:
                    continue
                Fa, Fb = F[a] - X[i] + X[j], F[b] - X[j] + X[i]
                na, nb = row_cost(Fa), row_cost(Fb)
                delta = na + nb - costs[a] - costs[b]
                if delta < 0 or rng.random() < np.exp(-delta / temp):
                    F[a], F[b], costs[a], costs[b] = Fa, Fb, na, nb
                    assign[i], assign[j] = b, a
        total = float(costs.sum())
        if total < best_total:
            best_assign, best_total = assign.copy(), total
    return best_assign, best_total


def main() -> None:
    df = P.load_all()
    frame = P.pool(df)
    X, cust_ids = customer_matrix(frame)
    out = frame[["id", "customer_id", "request_type", "escalation_label", "language", "adversarial", "split"]].rename(
        columns={"split": "original_split"})
    meta = dict(created=dt.datetime.now().isoformat(timespec="seconds"), dataset_sha256=P.EXPECTED_SHA256,
                n_chats=len(frame), n_customers=len(cust_ids), n_folds=K, group="customer_id",
                method="simulated annealing over customers", restarts=RESTARTS, iterations=ITERS,
                numpy=np.__version__, reps={})
    for rep in range(N_REPS):
        seed = 894 + rep
        assign, total = optimise(X, np.random.default_rng(seed))
        fold_of = dict(zip(cust_ids, assign))
        folds = frame["customer_id"].map(fold_of).astype(int).values
        # hard checks
        assert len(folds) == len(frame) and (folds >= 0).all(), "a chat has no fold"
        per_cust = pd.DataFrame({"c": frame["customer_id"], "f": folds}).groupby("c")["f"].nunique()
        assert (per_cust == 1).all(), "a customer is split across folds"
        out[f"rep{rep}"] = folds
        meta["reps"][f"rep{rep}"] = dict(seed=seed, objective=round(total, 4))
    P.FOLDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(P.FOLDS_PATH, index=False)
    (P.FOLDS_PATH.parent / "folds_v1.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("Saved", P.FOLDS_PATH)
    print(json.dumps(meta["reps"], indent=2))
    for rep in range(N_REPS):
        t = frame.assign(fold=out[f"rep{rep}"].values)
        print(f"\nrep{rep}: chats / escalations / adversarial / French / type min-max per fold")
        for k in range(K):
            s = t[t["fold"] == k]
            tc = s["request_type"].value_counts().reindex(P.REQUEST_TYPES, fill_value=0)
            print(f"  fold {k}: {len(s):3d} / {int(s['escalation_label'].sum()):2d} / {int(s['adversarial'].sum()):2d} / "
                  f"{int((s['language'] == 'fr').sum()):2d} / {int(tc.min())}-{int(tc.max())}")


if __name__ == "__main__":
    main()
