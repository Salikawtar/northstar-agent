"""Diversity numbers and the split check (data task 21)."""
import pandas as pd

from northstar.data import load_conversations
from northstar.datagen import split as sp_split
from northstar.datagen.diversity import distinct_n, mask_faker, report

DF = load_conversations()


def test_faker_values_are_masked_before_measuring():
    row = DF.iloc[0]
    first = row.faker_customer_name.split()[0]
    text = f"Hi, I'm {row.faker_customer_name}, plate {row.faker_plate}. {first} here again."
    masked = mask_faker(text, row)
    assert row.faker_plate not in masked and first not in masked and "<plate>" in masked


def test_distinct_n_counts_repetition():
    assert distinct_n(["the car the car the car"], 1) == round(2 / 6, 3)
    assert distinct_n(["a b c", "d e f"], 2) == 1.0


def test_diversity_report_has_the_numbers_page_2_uses():
    r = report()
    cm = r["customer_messages"]
    assert cm["n"] == 200 and 0 < cm["distinct_2"] <= 1 and 0 <= cm["similarity_mean"] < 0.5
    assert set(r["customer_messages_by_language"]) == {"en", "fr"}
    assert r["names"]["unique_names"] == r["names"]["customers"]


def test_current_split_is_protected():
    r = sp_split.check(DF)
    assert r["ok"] and r["customers_in_two_splits"] == 0
    assert r["sizes"] == {"train": 130, "validation": 30, "test": 40}
    assert all(p["near_copies"] == 0 for p in r["near_copies_across_splits"].values())
    assert len(r["attack_types_in_test"]) == 5


def test_check_catches_a_customer_in_two_splits_and_a_near_copy():
    bad = DF.copy()
    t = bad.index[bad.split == "test"][0]
    tr = bad.index[bad.split == "train"][0]
    bad.loc[tr, "customer_id"] = bad.loc[t, "customer_id"]            # same customer on both sides
    bad.loc[tr, "turn_1_customer"] = bad.loc[t, "turn_1_customer"]    # and the same opening message
    for col in ("faker_customer_name", "faker_plate", "faker_ro_number"):
        bad.loc[tr, col] = bad.loc[t, col]
    r = sp_split.check(bad)
    assert not r["ok"] and r["customers_in_two_splits"] >= 1
    assert r["near_copies_across_splits"]["train_vs_test"]["near_copies"] >= 1


def test_split_is_rebuilt_exactly_from_the_replay_and_the_logged_moves():
    split, moves = sp_split.rebuild()
    assert len(moves) == 32
    assert {i: s for i, s in DF.set_index("id").split.items()} == split
