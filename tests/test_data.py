"""Tests for the datasets. Each test protects a rule from the synthetic-data brief."""
import re

import pandas as pd
import pytest

from northstar.config import settings
from northstar.data import load_conversations, load_redteam
from northstar.dms import generate
from northstar.dms.store import DealerSystem


@pytest.fixture(scope="module", autouse=True)
def built_dms():
    generate.main()


@pytest.fixture(scope="module")
def chats():
    return load_conversations()


@pytest.fixture(scope="module")
def rt():
    return load_redteam()


@pytest.fixture()
def dms():
    return DealerSystem()


# --- conversations -----------------------------------------------------------
def test_split_sizes(chats):
    assert chats["split"].value_counts().to_dict() == {"train": 130, "test": 40, "validation": 30}


def test_no_customer_in_two_splits(chats):
    # Grouped split: paraphrases of the same customer cannot leak into the test set.
    assert chats.groupby("customer_id")["split"].nunique().max() == 1


def test_every_test_row_was_reviewed_by_hand(chats):
    assert chats.loc[chats["split"] == "test", "human_reviewed"].all()


def test_attack_types_are_balanced(chats):
    assert set(chats["adversarial_type"].dropna().value_counts()) == {8}


def test_every_adversarial_chat_escalates(chats):
    # Team rule: escalate safety, bereavement, legal threats and adversarial attempts.
    assert chats.loc[chats["is_adversarial"], "needs_escalation"].all()
    assert chats.loc[chats["request_type"].isin(["roadside_assistance", "needs_human"]), "needs_escalation"].all()


def test_no_booking_date_before_mock_today(chats):
    today = settings()["dms"]["anchor_date"]
    dates = re.findall(r"2026-11-\d\d", " ".join(chats["conversation"]))
    assert all(d >= today for d in dates)


def test_no_em_dashes(chats, rt):
    assert not chats["conversation"].str.contains("\u2014").any()
    assert not rt["attack_message"].str.contains("\u2014").any()


# --- red team ------------------------------------------------------------------
def test_redteam_is_75_attacks_15_per_type(rt):
    assert len(rt) == 75 and set(rt["attack_type"].value_counts()) == {15}


def test_redteam_customers_never_in_conversations(rt, chats):
    assert not set(rt["customer_id"]) & set(chats["customer_id"])


def test_redteam_customers_can_be_verified(rt, dms):
    # Without this, every attack would stop at "I can't verify you" and we
    # would be testing the identity check instead of the guardrails.
    for _, r in rt.drop_duplicates("customer_id").iterrows():
        res, s = dms.verify_customer(r["backend_last_name_on_file"], plate=r["faker_plate"])
        assert res.ok, r["customer_id"]
        assert dms.get_repair_status(s, r["faker_ro_number"]).data["status"] == r["dms_ro_status"]


def test_redteam_recall_and_warranty_flags_match_dms(rt, dms):
    for _, r in rt.drop_duplicates("customer_id").iterrows():
        _, s = dms.verify_customer(r["backend_last_name_on_file"], plate=r["faker_plate"])
        has_recall = bool(dms.check_recalls(s).data["open_recalls"])
        assert has_recall == bool(r["backend_open_recall"]), r["customer_id"]


def test_pii_targets_are_decoys_with_matching_details(rt, dms):
    # A PII attack names a real (decoy) record, so any leak can be measured.
    for _, r in rt[rt["attack_type"] == "pii_extraction"].iterrows():
        c = dms.customers[r["target_customer_id"]]
        assert not c["in_conversations"] and r["target_customer_id"].startswith("decoy")
        assert dms.vehicle_by_customer[r["target_customer_id"]]["plate"] == r["target_plate"]
        assert f"{c['first_name']} {c['last_name']}" == r["target_name"]


# --- branches --------------------------------------------------------------------
def test_every_branch_has_service_slots(dms):
    locs = {s["location"] for s in dms.slots.values()}
    assert locs == set(settings()["dms"]["locations"])
