"""Diversity of the 200 conversations, in numbers (data task: "realism and diversity").

The course guide suggests measuring diversity instead of eyeballing it. This reports, for the
customer messages (and separately for the agent replies):
- distinct-1 / distinct-2: unique words (or word pairs) divided by all words (or pairs).
  Higher = less repetition. It falls as a corpus grows, so only compare groups of similar size.
- mean pairwise similarity: TF-IDF cosine between every pair of conversations (0 = nothing in
  common, 1 = identical). Lower = more varied. Also the share of pairs above 0.5, and the most
  similar pair, so the worst case is visible.
- names: how many customer names are unique.

Faker values (names, plates, VINs, phones, emails, repair orders) are masked first, so the
numbers measure the writing, not the random fill.

Run:  python -m northstar.datagen.diversity
"""
from __future__ import annotations

import json
import re
import sys
from typing import Iterable

import numpy as np
import pandas as pd

from northstar.data import load_conversations

FAKER_COLS = ["faker_customer_name", "faker_email", "faker_phone", "faker_vin", "faker_plate", "faker_ro_number"]


def mask_faker(text: str, row: pd.Series) -> str:
    """Replace the row's own Faker values by a fixed token."""
    out = str(text)
    for col in FAKER_COLS:
        val = row.get(col)
        if isinstance(val, str) and val.strip():
            parts = [val] + (val.split() if col == "faker_customer_name" else [])
            for p in sorted(set(parts), key=len, reverse=True):
                if len(p) > 2:
                    out = re.sub(re.escape(p), f"<{col.replace('faker_', '')}>", out, flags=re.I)
    return out


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+|<\w+>", text.lower())


def distinct_n(texts: Iterable[str], n: int) -> float:
    grams, total = set(), 0
    for t in texts:
        toks = _tokens(t)
        g = [tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)]
        grams.update(g)
        total += len(g)
    return round(len(grams) / total, 3) if total else 0.0


def pairwise(texts: list[str], ids: list[str]) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    if len(texts) < 2:
        return {}
    X = TfidfVectorizer(token_pattern=r"[a-zàâçéèêëîïôûùüÿœ']+|<\w+>", lowercase=True).fit_transform(texts)
    sim = cosine_similarity(X)
    iu = np.triu_indices(len(texts), k=1)
    vals = sim[iu]
    k = int(vals.argmax())
    return dict(mean=round(float(vals.mean()), 3), share_above_0_5=round(float((vals > 0.5).mean()), 4),
                max=round(float(vals[k]), 3), most_similar_pair=[ids[iu[0][k]], ids[iu[1][k]]])


def measure(df: pd.DataFrame, column: str) -> dict:
    texts = [mask_faker(t, r) for t, (_, r) in zip(df[column].fillna(""), df.iterrows())]
    return dict(n=len(df), distinct_1=distinct_n(texts, 1), distinct_2=distinct_n(texts, 2),
                words_per_conversation=round(float(np.mean([len(_tokens(t)) for t in texts])), 1),
                **{f"similarity_{k}": v for k, v in pairwise(texts, df["id"].tolist()).items()})


def report(df: pd.DataFrame | None = None) -> dict:
    df = load_conversations() if df is None else df
    by = lambda col: {str(k): measure(g, "customer_text") for k, g in df.groupby(col)}
    names = df.drop_duplicates("customer_id").faker_customer_name
    return dict(
        customer_messages=measure(df, "customer_text"),
        agent_replies=measure(df, "turn_2_agent"),
        customer_messages_by_language=by("language"),
        customer_messages_by_request_type=by("request_type"),
        customer_messages_by_persona=by("customer_type"),
        names=dict(customers=int(df.customer_id.nunique()), unique_names=int(names.nunique()),
                   unique_first_names=int(names.str.split().str[0].nunique())),
        realism_controls={k: int(v) for k, v in df.realism_controls.fillna("").str.split(", ").explode()
                          .replace("", np.nan).dropna().value_counts().items()},
    )


def _main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    r = report()
    print(json.dumps({k: r[k] for k in ("customer_messages", "agent_replies", "names", "realism_controls")},
                     indent=1, ensure_ascii=False))
    print("\nCustomer messages by language / persona (distinct-2, mean similarity):")
    for key in ("customer_messages_by_language", "customer_messages_by_persona"):
        for g, m in r[key].items():
            print(f"  {g[:55]:55} n={m['n']:3}  distinct-2={m['distinct_2']:.3f}  similarity={m['similarity_mean']:.3f}")


if __name__ == "__main__":
    _main()
