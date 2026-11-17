"""Export a pipeline run as a CSV with the same columns as data/conversations/conversations.csv, and diff the two.

    python -m northstar.datagen.export                 # outputs/datagen/{train,test}.jsonl -> outputs/datagen/conversations_generated.csv
    python -m northstar.datagen.export --diff          # ... and compare it, row by row, with data/conversations/conversations.csv

The diff is the bridge between the generation run and the dataset the team uses: the ids, customers and request types
must match exactly; the text and the escalation labels differ where the QC_log sheet of the review workbook says they
were changed (em dashes removed, agent replies that promised coverage rewritten, team-review fixes, relabelling).
Nothing here writes to data/: the generated CSV goes to outputs/.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from northstar.config import ROOT, path
from northstar.datagen import pipeline as sp

COLUMNS = ["id", "split", "request_type", "difficulty", "hard_mode", "is_adversarial", "adversarial_type", "customer_type",
           "language", "code_switched", "has_correction", "realism_controls", "needs_escalation",
           "turn_1_customer", "turn_2_agent", "turn_3_customer", "conversation", "customer_text", "customer_id",
           "faker_customer_name", "faker_email", "faker_phone", "faker_vin", "faker_plate", "faker_ro_number"]


def to_dataset_layout(df: pd.DataFrame, split: str | None = None) -> pd.DataFrame:
    """Pipeline records (one row per conversation, `turns` as a list) -> the dataset's flat column layout."""
    def turn(t, i):
        return t[i]["text"] if isinstance(t, list) and len(t) > i else ""
    slots = df["faker_slots"].apply(lambda s: s if isinstance(s, dict) else {})
    out = pd.DataFrame({
        "id": df["id"], "split": split if split else df.get("split", ""),
        "request_type": df["intent"], "difficulty": df["difficulty"], "hard_mode": df["hard_mode"],
        "is_adversarial": df["is_adversarial"].astype(bool), "adversarial_type": df["adversarial_type"],
        "customer_type": df["persona"], "language": df["lang"], "code_switched": df["code_switched"].astype(bool),
        "has_correction": df["has_correction"].astype(bool),
        "realism_controls": df["realism_controls"].apply(lambda l: ", ".join(l) if isinstance(l, list) else ""),
        "needs_escalation": df["needs_escalation"].astype(bool),
        "turn_1_customer": df["turns"].apply(lambda t: turn(t, 0)), "turn_2_agent": df["turns"].apply(lambda t: turn(t, 1)),
        "turn_3_customer": df["turns"].apply(lambda t: turn(t, 2)),
        "conversation": df["conversation"], "customer_text": df["customer_text"], "customer_id": df["group"],
        "faker_customer_name": slots.apply(lambda s: s.get("customer_name")), "faker_email": slots.apply(lambda s: s.get("email")),
        "faker_phone": slots.apply(lambda s: s.get("phone")), "faker_vin": slots.apply(lambda s: s.get("vin")),
        "faker_plate": slots.apply(lambda s: s.get("plate")), "faker_ro_number": slots.apply(lambda s: s.get("ro_number")),
    })
    return out[COLUMNS].sort_values("id").reset_index(drop=True)


def load_run(run_dir: Path) -> pd.DataFrame:
    parts = []
    for split in ("train", "test"):
        f = run_dir / f"{split}.jsonl"
        if f.exists():
            parts.append(to_dataset_layout(sp.load_jsonl(str(f)), split))
    if not parts:                                   # a run without a split: kept.jsonl only
        parts.append(to_dataset_layout(sp.load_jsonl(str(run_dir / "kept.jsonl"))))
    return pd.concat(parts, ignore_index=True).sort_values("id").reset_index(drop=True)


def _norm(s: pd.Series) -> pd.Series:
    # Excel round-trips give the dataset CRLF line breaks inside cells; the pipeline writes LF. Not a content change.
    return (s.fillna("").astype(str).str.replace("\r\n", "\n").str.strip()
            .replace({"True": "TRUE", "False": "FALSE", "nan": ""}))


def _punctuation_only(a: str, b: str) -> bool:
    strip = lambda x: re.sub("[\\s\u2014,.;:!?-]+", " ", str(x)).strip().lower()
    return strip(a) == strip(b)


def diff(generated: pd.DataFrame, dataset: pd.DataFrame) -> dict:
    """Row-by-row comparison on the shared columns. Returns the numbers; prints a readable summary."""
    m = generated.merge(dataset, on="id", how="outer", suffixes=("_gen", "_data"), indicator=True)
    res = {"ids_only_in_generated": int((m["_merge"] == "left_only").sum()),
           "ids_only_in_dataset": int((m["_merge"] == "right_only").sum()), "per_column": {}}
    m = m[m["_merge"] == "both"]
    for c in COLUMNS[1:]:
        if f"{c}_gen" in m and f"{c}_data" in m:
            res["per_column"][c] = int((_norm(m[f"{c}_gen"]) != _norm(m[f"{c}_data"])).sum())
    text_changed = pd.Series(False, index=m.index)
    punct_only = pd.Series(True, index=m.index)
    for c in ("turn_1_customer", "turn_2_agent", "turn_3_customer"):
        a, b = _norm(m[f"{c}_gen"]), _norm(m[f"{c}_data"])
        ch = a != b
        text_changed |= ch
        punct_only &= (~ch) | pd.Series([_punctuation_only(x, y) for x, y in zip(a, b)], index=m.index)
    res["conversations_with_text_changes"] = int(text_changed.sum())
    res["of_which_punctuation_only"] = int((text_changed & punct_only).sum())
    res["of_which_rewritten"] = int((text_changed & ~punct_only).sum())
    print(f"ids: {len(m)} in both | only in generated {res['ids_only_in_generated']} | only in dataset {res['ids_only_in_dataset']}")
    print("rows that differ per column:")
    for c, n in res["per_column"].items():
        print(f"  {c:<20} {n:>4}")
    print(f"conversations with any turn text changed: {res['conversations_with_text_changes']} "
          f"(punctuation only {res['of_which_punctuation_only']}, rewritten {res['of_which_rewritten']})")
    return res


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", default="outputs/datagen", help="pipeline output folder (train/test or kept .jsonl)")
    p.add_argument("--out", default=None, help="CSV to write (default: <run>/conversations_generated.csv)")
    p.add_argument("--diff", action="store_true", help="compare with the dataset in data/conversations/")
    a = p.parse_args(argv)
    run_dir = ROOT / a.run
    gen = load_run(run_dir)
    out = Path(a.out) if a.out else run_dir / "conversations_generated.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    gen.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"wrote {out}: {len(gen)} rows, {gen['split'].value_counts().to_dict()}")
    if a.diff:
        diff(gen, pd.read_csv(path("conversations")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
