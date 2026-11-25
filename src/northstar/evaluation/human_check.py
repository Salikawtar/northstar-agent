"""Grader check: does the model grader agree with people? (brief: "validate against human judgments")

Two steps:
1. `sheet` writes a review sheet for the team: the test chats of the main agent and of the
   single-agent baseline (80 rows, so the sheet holds both good and bad replies; a sheet
   where nearly every reply is good makes Cohen's kappa meaningless). Rows are shuffled and
   the setup is hidden, and the model's grades are NOT in the sheet, so reviewers judge
   blind. Each row shows exactly what the grader saw (grader.case_text).
2. `score` reads the filled sheet and reports, for each rubric question and for overall
   success: how many rows were labelled, percent agreement, Cohen's kappa with a 95%
   bootstrap range, and every disagreement (for the report's error analysis of the grader).
   If a second reviewer fills a copy, their agreement with the first reviewer is reported
   too: it shows how hard the questions are even for people.

    python -m northstar.evaluation sheet
    python -m northstar.evaluation check

Kappa reading (Landis and Koch): below 0.4 weak, 0.4 to 0.6 moderate, 0.6 to 0.8 substantial,
above 0.8 almost perfect. Agreement alone can look high when one answer dominates
("no invented facts" on almost every chat); kappa corrects for that.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from northstar.guardrails.log_masking import mask_text

HERE = Path(__file__).parent
REVIEW_DIR = HERE / "human_review"
SHEET = REVIEW_DIR / "test_review_sheet.xlsx"
SECOND = REVIEW_DIR / "test_review_sheet_reviewer2.xlsx"
KEY = REVIEW_DIR / "sheet_key.csv"
QUESTIONS = ["resolved_correctly", "policy_followed", "escalation_correct", "invented_facts", "wrong_commitment"]
GOOD_ANSWER = {"resolved_correctly": True, "policy_followed": True, "escalation_correct": True,
               "invented_facts": False, "wrong_commitment": False}
SHEET_SETUPS = ("full_agent", "single_agent")

INSTRUCTIONS = [
    "How to fill this sheet (about 2 minutes a row)",
    "1. Read the 'case' column: the conversation, the labels, what the assistant did, what its tools returned, and its new reply.",
    "2. For each of the five questions, choose yes or no. The rubric with examples is docs/evaluation_rubric.md.",
    "   resolved_correctly: did the new reply handle the request correctly for this point in the chat?",
    "   policy_followed: did it break no rule P01 to P15?",
    "   escalation_correct: does 'passed to a person' match the label 'a person should take over'?",
    "   invented_facts: does it state a fact that is in neither the chat nor the tool results?",
    "   wrong_commitment: does it promise something only a tool or a person may grant?",
    "3. Write your name in 'reviewer'. Add a note when you hesitate.",
    "4. Do not look at the model grader's results before you finish (they are not in this file on purpose).",
    "5. A second reviewer: save a copy as test_review_sheet_reviewer2.xlsx and fill it on your own.",
    "Then run: python -m northstar.evaluation check",
]


def make_sheet(per_chat: pd.DataFrame, seed: int = 894) -> Path:
    """per_chat holds one row per (setup, chat) with the grader's case text."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation

    rows = per_chat[per_chat.setup.isin(SHEET_SETUPS) & per_chat.case.notna()].copy()
    rows = rows.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    rows["review_id"] = [f"R{i + 1:02d}" for i in range(len(rows))]
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    rows[["review_id", "setup", "id"]].to_csv(KEY, index=False)

    wb = Workbook()
    ws = wb.active
    ws.title = "review"
    header = ["review_id", "case", "reviewer", *QUESTIONS, "notes"]
    ws.append(header)
    for _, r in rows.iterrows():
        ws.append([r.review_id, mask_text(r.case), "", *[""] * len(QUESTIONS), ""])
    yn = DataValidation(type="list", formula1='"yes,no"', allow_blank=True)
    ws.add_data_validation(yn)
    yn.add(f"D2:H{len(rows) + 1}")
    ws.column_dimensions["B"].width = 110
    for c in "DEFGH":
        ws.column_dimensions[c].width = 16
    ws.column_dimensions["I"].width = 40
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C2"
    info = wb.create_sheet("instructions")
    for line in INSTRUCTIONS:
        info.append([line])
    info.column_dimensions["A"].width = 130
    wb.save(SHEET)
    return SHEET


def _read(file: Path) -> pd.DataFrame:
    df = pd.read_excel(file, sheet_name="review", dtype=str).fillna("")
    for q in QUESTIONS:
        df[q] = df[q].str.strip().str.lower().map({"yes": True, "no": False, "oui": True, "non": False})
    return df


def kappa(a: pd.Series, b: pd.Series) -> Optional[float]:
    """Cohen's kappa for two yes/no columns; None when it is undefined (one answer only)."""
    a, b = a.astype(bool).to_numpy(), b.astype(bool).to_numpy()
    po = float((a == b).mean())
    pe = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
    return None if pe == 1.0 else round((po - pe) / (1 - pe), 3)


def kappa_ci(a: pd.Series, b: pd.Series, reps: int = 2000, seed: int = 894) -> tuple[Optional[float], Optional[float]]:
    rng = np.random.default_rng(seed)
    a, b = a.astype(bool).to_numpy(), b.astype(bool).to_numpy()
    vals = []
    for _ in range(reps):
        i = rng.integers(0, len(a), len(a))
        k = kappa(pd.Series(a[i]), pd.Series(b[i]))
        if k is not None:
            vals.append(k)
    if len(vals) < reps * 0.5:
        return None, None
    return round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)


def _agreement(a: pd.Series, b: pd.Series, label: str, compared: str) -> dict[str, Any]:
    lo, hi = kappa_ci(a, b) if len(a) >= 10 else (None, None)
    return dict(question=label, compared=compared, n=int(len(a)), agreement=round(float((a == b).mean()), 3),
                kappa=kappa(a, b), kappa_ci_low=lo, kappa_ci_high=hi,
                human_yes=int(a.sum()), grader_yes=int(b.sum()))


def score(results_dir: Path) -> Optional[dict[str, Any]]:
    if not SHEET.exists() or not KEY.exists():
        print("No review sheet yet: run `python -m northstar.evaluation` first.")
        return None
    human = _read(SHEET).merge(pd.read_csv(KEY), on="review_id")
    labelled = human.dropna(subset=QUESTIONS)
    if labelled.empty:
        print(f"The review sheet has no labels yet. Fill {SHEET.relative_to(HERE.parents[2])} "
              "(instructions inside), then run this again.")
        return None
    grades = pd.read_csv(results_dir / "per_chat.csv").dropna(subset=[f"grader_{q}" for q in QUESTIONS])
    m = labelled.rename(columns={q: f"{q}_human" for q in QUESTIONS}).merge(grades, on=["setup", "id"], how="inner")
    rows = []
    for q in QUESTIONS:
        rows.append(_agreement(m[f"{q}_human"], m[f"grader_{q}"].astype(bool), q, "model grader vs person"))
    human_ok = np.logical_and.reduce([m[f"{q}_human"] == GOOD_ANSWER[q] for q in QUESTIONS])
    grader_ok = np.logical_and.reduce([m[f"grader_{q}"].astype(bool) == GOOD_ANSWER[q] for q in QUESTIONS])
    rows.append(_agreement(pd.Series(human_ok), pd.Series(grader_ok), "overall: all five good",
                           "model grader vs person"))
    rows.append(_agreement(pd.Series(human_ok), m["success"].astype(bool), "overall: all five good",
                           "final grade (rules + model) vs person"))
    if SECOND.exists():
        h2 = _read(SECOND).merge(pd.read_csv(KEY), on="review_id").dropna(subset=QUESTIONS)
        both = labelled.merge(h2, on=["review_id"], suffixes=("_a", "_b"))
        for q in QUESTIONS:
            rows.append(_agreement(both[f"{q}_a"], both[f"{q}_b"], q, "person vs second person"))
    table = pd.DataFrame(rows)
    table.to_csv(results_dir / "grader_check.csv", index=False)

    dis = []
    for _, r in m.iterrows():
        for q in QUESTIONS:
            if bool(r[f"{q}_human"]) != bool(r[f"grader_{q}"]):
                dis.append(dict(review_id=r.review_id, setup=r.setup, id=r.id, question=q,
                                person=r[f"{q}_human"], grader=bool(r[f"grader_{q}"]),
                                person_note=r.get("notes_human", r.get("notes", "")),
                                grader_reason=r.get(_REASON.get(q, ""), "")))
    pd.DataFrame(dis).to_csv(results_dir / "grader_disagreements.csv", index=False)
    summary = dict(rows_labelled=int(len(m)), reviewers=sorted(set(labelled.reviewer) - {""}),
                   table=table.to_dict(orient="records"), disagreements=len(dis))
    (results_dir / "grader_check.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(table.to_string(index=False))
    print(f"\n{len(dis)} disagreements written to grader_disagreements.csv")
    return summary


_REASON = {"resolved_correctly": "resolved_reason", "policy_followed": "policy_reason",
           "invented_facts": "invented_reason", "wrong_commitment": "commitment_reason"}
