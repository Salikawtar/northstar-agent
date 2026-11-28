"""The fixed rules of the comparison: one place that every script reads.

Nothing here trains a model. It defines the labels, the input variants, the seeds, the
dataset check, the saved cross-validation folds, and the lock on the 40 test chats.

Why a lock: the test chats are scored once, at the very end. `pool()` returns only the 160
train + validation chats, so ordinary code never sees the test rows. `test_set()` refuses to
return them unless the caller says `final=True` AND the environment variable
NORTHSTAR_ALLOW_TEST=1 is set, and it writes a line to study/results/test_access.log (the Kaggle final run kept its own copy in results/step06/) each time.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]          # the team repo
STUDY = Path(__file__).resolve().parent             # this study: config, folds, results, notebooks, docs
DATA_PATH = ROOT / "data" / "conversations" / "conversations.csv"
FOLDS_PATH = STUDY / "data" / "folds" / "folds_v1.csv"
TEST_LOG = STUDY / "results" / "test_access.log"
FRESH_PATH = ROOT / "data" / "fresh" / "fresh_chats.csv"

# Hashes are taken with Windows line endings turned into plain ones, so a checkout on any system passes.
# Hash of the team's dataset (v1114, team repo commit 9b118f8). See study/data/README.md.
EXPECTED_SHA256 = "593de5bd3d2908f399d0d04da42f1a634ae3caafe8dd58bc3e435a824f0ad119"
# Hash of the team's fresh held-out set (32 chats, 1 rejected in review; team repo commit 0cc6208). See study/data/README.md.
EXPECTED_FRESH_SHA256 = "a2d32933d86e4de6dc022fa02e027a3ce281ab6201715b5516c199f0c3120c9e"

# Same values and order as the team's contracts.py (RequestType, EscalationReason, Language).
REQUEST_TYPES = [
    "book_service", "repair_status", "warranty_claim", "recall_inquiry",
    "roadside_assistance", "parts_order", "billing_dispute", "lease_end_return",
    "out_of_scope", "needs_human",
]
# The reasons a router is responsible for. The other reasons (verification_failed,
# tool_failure, low_confidence) are set by the pipeline code, not by the router.
REASONS = ["none", "safety", "bereavement", "legal_threat", "adversarial", "customer_request", "policy_limit"]
LANGUAGES = ["en", "fr"]

# The three inputs every router is compared on (see docs/EVAL_PROTOCOL.md).
INPUT_VARIANTS = ("first_message", "customer_turns", "full_conversation")

N_FOLDS = 5
CV_SEEDS = (11, 22, 33)          # training seeds used in cross-validation
FINAL_SEEDS = (101, 102, 103, 104, 105)  # training seeds for the final models


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_all(path: Path = DATA_PATH, check_hash: bool = True) -> pd.DataFrame:
    """All 200 chats with integer labels added. Refuses to run on a different dataset file."""
    if check_hash and sha256_of(path) != EXPECTED_SHA256:
        raise ValueError(
            f"{path} is not the dataset this protocol was written for (hash mismatch). "
            "Re-copy the team file and update EXPECTED_SHA256 and data/README.md on purpose.")
    return _add_labels(pd.read_csv(path, encoding="utf-8-sig"))


def _add_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Integer labels for the model, from the dataset's own columns."""
    df["type_label"] = df["request_type"].map({t: i for i, t in enumerate(REQUEST_TYPES)})
    assert df["type_label"].notna().all(), "a request_type is not in REQUEST_TYPES"
    df["type_label"] = df["type_label"].astype(int)
    df["escalation_label"] = df["needs_escalation"].astype(bool).astype(int)
    df["language_label"] = df["language"].map({l: i for i, l in enumerate(LANGUAGES)}).astype(int)
    df["adversarial"] = df["is_adversarial"].fillna(False).astype(bool)
    # Attack yes/no, as the team grader decides it (evaluation/rules.py): a non-empty adversarial_type.
    df["attack_label"] = df["adversarial_type"].apply(lambda v: int(isinstance(v, str) and bool(v)))
    return df


def pool(df: pd.DataFrame) -> pd.DataFrame:
    """The 160 train + validation chats. The test chats are not in here."""
    out = df[df["split"].isin(["train", "validation"])].reset_index(drop=True)
    assert len(out) == 160 and not (out["split"] == "test").any()
    return out


def input_text(df: pd.DataFrame, variant: str) -> pd.Series:
    """The text a router reads, for one of the three input variants.

    first_message     : the customer's first message only (what a router sees in production).
    customer_turns    : the customer's first and last messages (what the original notebook used).
    full_conversation : customer, agent, customer, formatted exactly as the team's prompted
                        router formats it (`format_conversation` in agent/router.py).
    """
    if variant == "first_message":
        return df["turn_1_customer"].astype(str)
    if variant == "customer_turns":
        return df["turn_1_customer"].astype(str) + " " + df["turn_3_customer"].astype(str)
    if variant == "full_conversation":
        return ("Customer: " + df["turn_1_customer"].astype(str) + "\nAgent: " + df["turn_2_agent"].astype(str)
                + "\nCustomer: " + df["turn_3_customer"].astype(str))
    raise ValueError(f"unknown input variant {variant!r}; use one of {INPUT_VARIANTS}")


def fold_assignments(rep: int = 0) -> pd.DataFrame:
    """The saved folds for the 160-chat pool: columns id, fold (0..4). Same file on every machine."""
    f = pd.read_csv(FOLDS_PATH)
    col = f"rep{rep}"
    if col not in f.columns:
        raise ValueError(f"no repeat {rep} in {FOLDS_PATH}")
    return f[["id", col]].rename(columns={col: "fold"})


def test_set(df: pd.DataFrame, *, final: bool = False, note: str = "") -> pd.DataFrame:
    """The 40 test chats. Locked: only the final scoring step may call this."""
    if not (final and os.environ.get("NORTHSTAR_ALLOW_TEST") == "1"):
        raise PermissionError(
            "The test chats are locked until the final scoring step. "
            "Call test_set(..., final=True) with NORTHSTAR_ALLOW_TEST=1 set, and say why in `note`.")
    TEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(TEST_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{_dt.datetime.now().isoformat(timespec='seconds')} test set opened: {note or 'no note'}\n")
    return df[df["split"] == "test"].reset_index(drop=True)


def _log_access(what: str, note: str) -> None:
    TEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(TEST_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{_dt.datetime.now().isoformat(timespec='seconds')} {what} opened: {note or 'no note'}\n")


def fresh_set(*, final: bool = False, note: str = "") -> pd.DataFrame:
    """The team's fresh held-out set (generated by another model family after every fix, reviewed by two people,
    frozen): 31 chats once the one rejected in review is removed, as the team does. Locked like the test chats."""
    if not (final and os.environ.get("NORTHSTAR_ALLOW_TEST") == "1"):
        raise PermissionError("The fresh chats are locked like the test chats: final=True and NORTHSTAR_ALLOW_TEST=1.")
    if sha256_of(FRESH_PATH) != EXPECTED_FRESH_SHA256:
        raise ValueError(f"{FRESH_PATH} is not the frozen fresh set (hash mismatch).")
    _log_access("fresh set", note)
    df = pd.read_csv(FRESH_PATH, encoding="utf-8-sig")
    df = df[df["review_decision"] != "reject"].reset_index(drop=True)
    return _add_labels(df)
