"""Fresh held-out set: new chats nobody has looked at, for one final, honest run of the agent.

Why: the 40 test chats were read during the error analysis (D-32), so the 70% after the fixes is
optimistic. A new set, generated after every fix and run once, gives a score that nobody could
tune to. (D-33)

How the set was made (data/fresh/generation/):
- 40 jobs from the same coverage matrix and prompt v2 as the main dataset, new seed (2611), new
  customers (none shared with the 200 chats): `python -m northstar.datagen.pipeline --dump-jobs ...`
- Generator: Google Gemini 3.1 Pro, another family than the agents (Claude), the grader (OpenAI)
  and the main dataset's generator (Claude), so the set is not written in the agent's own style.
  A trial with the planned 8-model rotation of small models is kept in data/fresh/trial_rotation/:
  too many garbled or off-label chats (one roadside chat labelled out of scope, one unreadable).
- The pipeline's own checks (format, language, placeholders, near-copies) kept 32 of 40.

Steps:
    python -m northstar.datagen.fresh build     # kept.jsonl -> data/fresh/fresh_chats.csv + review sheet
    (two team members fill data/fresh/fresh_review.xlsx: keep / fix / reject, labels)
    python -m northstar.datagen.fresh freeze    # applies the review; the set is frozen
    python -m northstar.evaluation --split fresh --setups full_agent   # ONE run, no change afterwards

Escalation labels follow the team rule (docs/data_tasks.md, task 9): roadside, needs_human and
every attack need a person; a billing dispute needs one when it contests a charge (the generator's
label is kept there, for the reviewers to confirm); everything else does not.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from northstar.config import ROOT
from northstar.datagen import pipeline as sp
from northstar.datagen.export import to_dataset_layout

FRESH = ROOT / "data" / "fresh"
GEN = FRESH / "generation"
CSV = FRESH / "fresh_chats.csv"
SHEET = FRESH / "fresh_review.xlsx"
FROZEN = FRESH / "FROZEN.json"
REVIEW_COLS = ["decision", "request_type_ok", "correct_request_type", "escalation_ok", "notes"]


def team_label(row: pd.Series, generator_label: bool) -> bool:
    if row["request_type"] in ("roadside_assistance", "needs_human") or bool(row["is_adversarial"]):
        return True
    if row["request_type"] == "billing_dispute":
        return bool(generator_label)          # contests a charge or only asks about it: reviewers confirm
    return False


def build() -> None:
    if FROZEN.exists():
        sys.exit("The fresh set is frozen (data/fresh/FROZEN.json): it is not rebuilt.")
    kept = sp.load_jsonl(str(GEN / "kept.jsonl"))
    df = to_dataset_layout(kept, split="fresh")
    gen = dict(zip(kept["id"], kept["needs_escalation"].astype(bool)))
    df["generator_needs_escalation"] = df["id"].map(gen)
    df["needs_escalation"] = [team_label(r, gen[r["id"]]) for _, r in df.iterrows()]
    df["human_reviewed"], df["review_decision"] = False, ""
    df.to_csv(CSV, index=False)
    _sheet(df)
    print(f"{len(df)} chats -> {CSV.relative_to(ROOT)}; review sheet -> {SHEET.relative_to(ROOT)}")
    print(df.request_type.value_counts().to_string())


def _sheet(df: pd.DataFrame) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook()
    ws = wb.active
    ws.title = "review"
    head = ["id", "conversation", "request_type", "needs_escalation", "label_check_needed", *REVIEW_COLS]
    ws.append(head)
    for _, r in df.iterrows():
        check = "yes: generator said " + str(r.generator_needs_escalation) \
            if bool(r.generator_needs_escalation) != bool(r.needs_escalation) or r.request_type == "billing_dispute" else ""
        ws.append([r.id, str(r.conversation).replace("\r\n", "\n"), r.request_type,
                   "yes" if r.needs_escalation else "no", check, "", "", "", "", ""])
    n = len(df) + 1
    for col, opts in (("F", '"keep,fix,reject"'), ("G", '"yes,no"'), ("I", '"yes,no"')):
        dv = DataValidation(type="list", formula1=opts, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{n}")
    ws.column_dimensions["B"].width = 100
    for c, w in zip("ACDEFGHIJ", (10, 20, 12, 22, 10, 12, 20, 12, 40)):
        ws.column_dimensions[c].width = w
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C2"
    info = wb.create_sheet("instructions")
    for line in [
        "Fresh test set: check each chat BEFORE the agent is run on it (about 1 to 2 minutes a chat).",
        "decision: keep (good as it is), fix (keep, but a label is wrong: say which below), reject (unrealistic, garbled or not about the dealership).",
        "request_type_ok: is 'request_type' right for this chat? If no, write the right one in correct_request_type.",
        "   types: book_service, repair_status, warranty_claim, recall_inquiry, roadside_assistance, parts_order, billing_dispute, lease_end_return, out_of_scope, needs_human",
        "escalation_ok: is 'needs_escalation' right? Team rule: yes for roadside (safety), needs_human (bereavement, legal threat, asks for a manager),",
        "   every attempt to trick the assistant, and a billing dispute that contests a charge; no otherwise.",
        "label_check_needed: the generator's label disagreed with the team rule, or a dispute must be confirmed. Look at these first.",
        "Do not edit the conversation text. Do not look at any agent output: the agent has not been run on these chats, on purpose.",
    ]:
        info.append([line])
    info.column_dimensions["A"].width = 140
    wb.save(SHEET)


def freeze(sheets: list[Path]) -> None:
    """Apply the review (one or two filled sheets). A chat is dropped if any reviewer rejects it;
    a label is changed only when the reviewers who filled it agree on the new value."""
    df = pd.read_csv(CSV)
    reviews = [pd.read_excel(s, sheet_name="review", dtype=str).fillna("") for s in sheets]
    changes = []
    for i, r in df.iterrows():
        rows = [rv[rv.id == r.id].iloc[0] for rv in reviews if (rv.id == r.id).any()]
        if not rows or any(x.decision.strip() == "" for x in rows):
            sys.exit(f"{r.id} is not reviewed in every sheet: finish the review first.")
        if any(x.decision.strip() == "reject" for x in rows):
            df.at[i, "review_decision"] = "reject"
            continue
        new_types = {x.correct_request_type.strip() for x in rows if x.request_type_ok.strip() == "no"}
        if len(new_types) == 1 and all(x.request_type_ok.strip() == "no" for x in rows):
            changes.append(f"{r.id}: request_type {r.request_type} -> {next(iter(new_types))}")
            df.at[i, "request_type"] = next(iter(new_types))
        if all(x.escalation_ok.strip() == "no" for x in rows):
            changes.append(f"{r.id}: needs_escalation {r.needs_escalation} -> {not r.needs_escalation}")
            df.at[i, "needs_escalation"] = not bool(r.needs_escalation)
        df.at[i, "review_decision"] = "fix" if any(x.decision.strip() == "fix" for x in rows) else "keep"
        df.at[i, "human_reviewed"] = True
    kept = df[df.review_decision != "reject"]
    df.to_csv(CSV, index=False)
    FROZEN.write_text(json.dumps({"chats": int(len(kept)), "rejected": int((df.review_decision == "reject").sum()),
                                  "label_changes": changes, "reviewed_with": [s.name for s in sheets]}, indent=1),
                      encoding="utf-8")
    print(f"Frozen: {len(kept)} chats kept, {len(df) - len(kept)} rejected, {len(changes)} label changes.")
    for c in changes:
        print("  " + c)


def load_fresh() -> pd.DataFrame:
    """The frozen fresh set, rejected chats removed. Read through northstar.data.load_conversations('fresh')."""
    if not FROZEN.exists():
        raise RuntimeError("The fresh set is not frozen yet: review it, then `python -m northstar.datagen.fresh freeze`.")
    df = pd.read_csv(CSV)
    return df[df.review_decision != "reject"].reset_index(drop=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Build, review and freeze the fresh held-out set.")
    ap.add_argument("command", choices=["build", "freeze"])
    ap.add_argument("--sheets", nargs="*", default=[str(SHEET)], help="filled review sheets (one or two)")
    a = ap.parse_args()
    build() if a.command == "build" else freeze([Path(s) for s in a.sheets])


if __name__ == "__main__":
    main()
