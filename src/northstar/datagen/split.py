"""The 130 / 30 / 40 split: rebuild it from the record, and check that it is protected (results in docs/data_quality.md).

How the split was made (two steps, both logged):
1. The generation run cut 160 train / 40 test, grouped by customer and stratified by request
   type (`pipeline.make_splits`, replayed here from the recorded run).
2. On 2026-11-10 the team moved 30 train rows to a validation split (grouped by customer, seed 894)
   and swapped two single-customer rows so the test set holds a data-extraction attack
   (v3_0078 to test, v3_0215 to train). Each move is a row of the QC_log sheet of the workbook.

`--rebuild` replays the generation run, checks that the recorded 160 / 40 cut follows the run's own rules,
applies the logged moves of step 2 and compares the result with the `split` column of the dataset.

Why the cut is checked, not drawn again (2026-11-24): the fold StratifiedGroupKFold picks depends on the
scikit-learn version. On the versions tried (1.3 to 1.7, and the team's Windows setup) the replay picks a
different, less balanced fold (L1 0.32) than the generation run did (L1 0.05). The rows, customers and
request types do replay exactly (tests/test_datagen.py), so the recorded cut (dataset split plus the
logged moves, undone) is checked against the same rules instead: 160 / 40, no customer on both sides,
every request type in test, balance no worse than the recorded L1 of 0.05, no near-copy across.
The seed-894 draw of step 2 was made in a notebook and not kept as code, so step 2 is rebuilt from its log.

`--check` (default) proves the protection on the dataset as it is:
- no customer in two splits;
- no near-copy across splits: character n-gram similarity of the opening customer message, with the
  Faker values masked, below 0.8 for every pair (the generation run's own threshold);
- each split's mix of request types, languages and difficulty;
- every test conversation reviewed by hand.

Run:  python -m northstar.datagen.split            (check)
      python -m northstar.datagen.split --rebuild  (replay + logged moves, then compare)
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from itertools import combinations
from pathlib import Path

import openpyxl
import pandas as pd

from northstar.config import path
from northstar.data import load_conversations
from northstar.datagen import pipeline as sp
from northstar.datagen.diversity import mask_faker

THRESHOLD = 0.80
GEN = Path(__file__).resolve().parents[3] / "data" / "source" / "generation"


def logged_moves(workbook: Path | None = None) -> pd.DataFrame:
    """Split moves recorded in the workbook's QC_log sheet: id, from, to, rule."""
    wb = openpyxl.load_workbook(workbook or path("dataset_source"), read_only=True)
    rows = []
    for r in wb["QC_log"].iter_rows(values_only=True):
        if r and r[0] == "conversations" and len(r) >= 8 and r[3] == "split":
            rows.append(dict(id=r[1], rule=r[2], before=r[6], after=r[7]))
    return pd.DataFrame(rows)


RECORDED_L1 = 0.05      # balance of the generation run's test fold (run_manifest.json, split_check)
BALANCE_COLS = ("intent", "lang", "difficulty", "channel")


def replay_kept() -> pd.DataFrame:
    """Replay the generation run (no key, no network) and return the 200 kept rows."""
    with tempfile.TemporaryDirectory() as out:
        cfg = sp.Cfg()
        cfg.seed, cfg.out_dir, cfg.cache_dir = 42, out, str(Path(out) / "cache")
        cfg.jobs_file = str(GEN / "jobs_designed.jsonl")
        client = sp.LLMClient(generations=sp.load_generations(str(GEN / "generations_v3_conv.jsonl")),
                              generator_name="recorded run", cache_dir=cfg.cache_dir)
        res = sp.run_pipeline(cfg, client, verbose=False)
    return res["kept"].reset_index(drop=True)


def recorded_first_cut(df: pd.DataFrame, moves: pd.DataFrame) -> dict[str, str]:
    """The generation run's 160 / 40 cut: the dataset split with the logged moves undone."""
    now = df.set_index("id").split
    split = {i: ("train" if s == "validation" else s) for i, s in now.items()}
    for _, m in moves.iterrows():
        if now.get(m.id) != m.after:       # the log must describe the dataset as it is
            raise ValueError(f"{m.id}: log says it moved to {m.after}, the dataset has {now.get(m.id)}")
        split[m.id] = m.before
    return split


def check_first_cut(split: dict[str, str], kept: pd.DataFrame) -> dict:
    """Does the cut follow the generation run's rules? Same checks as pipeline.make_splits."""
    k = kept.assign(side=kept["id"].map(split))
    tr, te = k[k.side == "train"], k[k.side == "test"]
    l1 = sum(float((te[c].value_counts(normalize=True).reindex(k[c].value_counts(normalize=True).index, fill_value=0)
                    - k[c].value_counts(normalize=True)).abs().sum()) for c in BALANCE_COLS)
    _, max_sim = sp._cross_dup(tr["raw_message"].astype(str).tolist(), te["raw_message"].astype(str).tolist(),
                               THRESHOLD)
    r = dict(sizes=(len(tr), len(te)), unassigned=int(k.side.isna().sum()),
             customers_on_both_sides=len(set(tr["group"]) & set(te["group"])),
             request_types_missing_in_test=sorted(set(k["intent"]) - set(te["intent"])),
             l1_balance=round(l1, 3), max_cross_similarity=round(float(max_sim), 3))
    r["ok"] = bool(r["sizes"] == (160, 40) and not r["unassigned"] and not r["customers_on_both_sides"]
                   and not r["request_types_missing_in_test"] and l1 <= RECORDED_L1 + 1e-9 and max_sim < THRESHOLD)
    return r


def rebuild() -> tuple[dict[str, str], pd.DataFrame]:
    """Check the recorded 160 / 40 cut against the replayed rows, then apply the logged moves."""
    df, moves = load_conversations(), logged_moves()
    split = recorded_first_cut(df, moves)
    r = check_first_cut(split, replay_kept())
    if not r["ok"]:
        raise ValueError(f"the recorded 160 / 40 cut breaks the generation run's rules: {r}")
    for _, m in moves.iterrows():
        split[m.id] = m.after
    return split, moves


def check(df: pd.DataFrame | None = None) -> dict:
    df = load_conversations() if df is None else df
    from sklearn.metrics.pairwise import cosine_similarity
    by_customer = df.groupby("customer_id").split.nunique()
    openings = [sp._norm_template(mask_faker(t, r)) for t, (_, r) in zip(df.turn_1_customer.fillna(""), df.iterrows())]
    vec, X = sp._char_tfidf(openings)
    sim = cosine_similarity(X)
    pairs = {}
    for a, b in combinations(["train", "validation", "test"], 2):
        ia, ib = (df.split == a).to_numpy().nonzero()[0], (df.split == b).to_numpy().nonzero()[0]
        s = sim[ia][:, ib]
        i, j = divmod(int(s.argmax()), s.shape[1])
        pairs[f"{a}_vs_{b}"] = dict(max_similarity=round(float(s.max()), 3), near_copies=int((s >= THRESHOLD).sum()),
                                    closest=[df.id.iloc[ia[i]], df.id.iloc[ib[j]]])
    mix = {col: pd.crosstab(df[col], df.split).to_dict() for col in ("request_type", "language", "difficulty")}
    test = df[df.split == "test"]
    return dict(
        sizes={k: int(v) for k, v in df.split.value_counts().items()},
        customers_in_two_splits=int((by_customer > 1).sum()),
        near_copies_across_splits=pairs,
        test_reviewed_by_hand=f"{int(test.human_reviewed.sum())} of {len(test)}",
        attack_types_in_test=sorted(test.adversarial_type.dropna().loc[lambda s: s != ""].unique().tolist()),
        mix=mix,
        ok=bool((by_customer <= 1).all() and all(p["near_copies"] == 0 for p in pairs.values())
                and test.human_reviewed.all()),
    )


def _main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Check (default) or rebuild the 130 / 30 / 40 split.")
    ap.add_argument("--rebuild", action="store_true", help="replay the first split, apply the logged moves, compare")
    a = ap.parse_args()
    df = load_conversations()
    if a.rebuild:
        split, moves = rebuild()
        diff = [i for i, s in df.set_index("id").split.items() if split.get(i) != s]
        print(f"recorded 160 / 40 cut follows the run's rules, applied {len(moves)} logged moves: "
              f"{pd.Series(split).value_counts().to_dict()} | rows that differ from the dataset: {len(diff)} {diff[:10]}")
        if diff:
            sys.exit(1)
    r = check(df)
    print(json.dumps({k: v for k, v in r.items() if k != "mix"}, indent=1))
    print("PASS" if r["ok"] else "FAIL")
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    _main()
