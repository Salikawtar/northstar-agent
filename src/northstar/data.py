"""Load the project datasets. Every module reads data through here, so a file
move or format change only needs one edit.

- conversations: 200 three-turn chats (train 130 / validation 30 / test 40),
  grouped by customer so no customer appears in two splits.
- red team: 75 single-message attacks, never used for training or the
  accuracy test; only for guardrail pass rates.
Source of truth for both: data/source/northstar_synthetic_dataset_v1113.xlsx
(human review, QC log and decisions live there).
"""
from __future__ import annotations

import json

import pandas as pd

from northstar.config import path


def load_conversations(split: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(path("conversations"))
    return df if split is None else df[df["split"] == split].reset_index(drop=True)


def load_redteam() -> pd.DataFrame:
    return pd.read_csv(path("redteam"))


def load_redteam_dms() -> dict[str, list[dict]]:
    """Dealer records for the red-team customers, so attacks reach the guardrails."""
    d = path("redteam_dms_dir")
    return {n: json.load(open(d / f"dms_{n}.json", encoding="utf-8"))
            for n in ("customers", "vehicles", "repair_orders")}
