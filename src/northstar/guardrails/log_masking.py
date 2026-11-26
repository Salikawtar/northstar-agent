"""Mask personal data before anything is written to a results file (rule P11).

The outline promised that VINs and phone numbers are masked in logs. Every runner saves its
results through `save_results`, which masks the text columns:
- phone numbers  -> (***) ***-0198      (last 4 kept, so a person can still match a callback)
- email          -> j***@example.com
- VIN            -> *************5594   (last 4 kept)
- plate          -> C*** 609
- card or SIN numbers are already masked by the input check (G-IN-02); any left are removed here.

The replay cache (`data/llm_cache/`) keeps the full synthetic conversations, because it is the test
fixture that makes every run reproducible. It holds only synthetic data; a real deployment would not
keep raw prompts, or would mask them before storing (stated in docs/guardrails.md).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

_PHONE = re.compile(r"\(?\b(\d{3})\)?[ .-]?(\d{3})[ .-](\d{4})\b")
_EMAIL = re.compile(r"\b([\w.+-])[\w.+-]*@([\w-]+\.[\w.-]+)\b")
_VIN = re.compile(r"\b[A-HJ-NPR-Z0-9]{13}(\d{4})\b")
_PLATE = re.compile(r"\b([A-Z])[A-Z]{3} ?(\d{3})\b")
_LONG_NUMBER = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


def mask_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = _LONG_NUMBER.sub("[number removed]", text)
    text = _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)
    text = _VIN.sub(lambda m: "*" * 13 + m.group(1), text)
    text = _PHONE.sub(lambda m: f"(***) ***-{m.group(3)}", text)
    return _PLATE.sub(lambda m: f"{m.group(1)}*** {m.group(2)}", text)


def mask_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object or pd.api.types.is_string_dtype(out[col]):
            out[col] = out[col].map(mask_text)
    return out


def save_results(df: pd.DataFrame, file: Path) -> None:
    """The one way runners write a results table: masked, UTF-8, no index."""
    mask_frame(df).to_csv(file, index=False)
