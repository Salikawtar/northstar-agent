"""Tests for the mock dealer system. Each test name says which design rule it protects."""
import pandas as pd
import pytest

from northstar.config import path
from northstar.data import load_conversations
from northstar.contracts import ToolError
from northstar.dms import generate
from northstar.dms.store import DealerSystem


@pytest.fixture(scope="module", autouse=True)
def built_dms():
    generate.main()


@pytest.fixture()
def dms():
    return DealerSystem()


@pytest.fixture(scope="module")
def chats():
    return load_conversations()


def _a_customer(chats):
    r = chats.iloc[3]  # Jeffrey Howard, plate CBNY 079 (warranty question)
    return r["faker_customer_name"].split()[-1], r["faker_plate"], r["faker_ro_number"]


# --- generation ---------------------------------------------------------
def test_every_chat_customer_exists_in_dms(dms, chats):
    assert set(chats["customer_id"]) <= set(dms.customers)


def test_chat_identifiers_match_dms_records(dms, chats):
    for _, r in chats.drop_duplicates("customer_id").iterrows():
        v = dms.vehicles[r["faker_vin"]]
        assert v["plate"] == r["faker_plate"]
        assert dms.ros[r["faker_ro_number"]]["vin"] == r["faker_vin"]


def test_model_year_taken_from_conversation(dms, chats):
    r = chats.iloc[3]  # mentions "2021 Meridian Halden"
    v = dms.vehicles[r["faker_vin"]]
    assert (v["model"], v["year"]) == ("Halden", 2021)


def test_generation_is_deterministic():
    assert generate.build(seed=1) == generate.build(seed=1)


def test_decoys_are_never_in_conversations(dms, chats):
    decoys = {c for c, x in dms.customers.items() if not x["in_conversations"]}
    assert decoys and not decoys & set(chats["customer_id"])


def test_decoy_vins_have_valid_check_digit(dms):
    for v in dms.vehicles.values():
        if v["customer_id"].startswith("decoy"):
            assert v["vin"][8] == generate.vin_check_digit(v["vin"])


# --- verification is enforced in code ---------------------------------------
def test_verify_with_plate_and_last_name(dms, chats):
    ln, plate, _ = _a_customer(chats)
    res, s = dms.verify_customer(ln, plate=plate)
    assert res.ok and s is not None


def test_verify_tolerates_format_differences(dms, chats):
    ln, plate, _ = _a_customer(chats)
    res, s = dms.verify_customer(ln.upper(), plate=plate.lower().replace(" ", ""))
    assert res.ok


def test_verify_with_ro_number(dms, chats):
    ln, _, ro = _a_customer(chats)
    res, s = dms.verify_customer(ln, ro_number=ro)
    assert res.ok


def test_accented_names_match():
    assert generate.normalize_name("St-Laurent") == generate.normalize_name("st laurent")
    assert generate.normalize_name("Gagné") == generate.normalize_name("GAGNE")


def test_wrong_name_fails_without_revealing_which_part(dms, chats):
    _, plate, _ = _a_customer(chats)
    res, s = dms.verify_customer("Smithers", plate=plate)
    assert not res.ok and s is None and res.message == "Details do not match our records."
    res2, _ = dms.verify_customer("Smithers", plate="ZZZZ 999")
    assert res2.message == res.message  # same message: no enumeration


def test_lookup_without_session_is_unauthorized(dms, chats):
    _, _, ro = _a_customer(chats)
    assert dms.get_repair_status(None, ro).error == ToolError.UNAUTHORIZED
    assert dms.get_vehicle(None).error == ToolError.UNAUTHORIZED


def test_forged_session_is_rejected(dms, chats):
    from northstar.dms.store import Session
    fake = Session(token="deadbeef", customer_id="cust_en_31245", vin="X")
    assert dms.get_vehicle(fake).error == ToolError.UNAUTHORIZED


def test_session_cannot_read_another_customers_repair_order(dms, chats):
    ln, plate, _ = _a_customer(chats)
    _, s = dms.verify_customer(ln, plate=plate)
    other_ro = next(r for r in dms.ros.values() if r["customer_id"] != s.customer_id)["ro_number"]
    assert dms.get_repair_status(s, other_ro).error == ToolError.UNAUTHORIZED


# --- lookups ---------------------------------------------------------------
def test_repair_status_for_own_order(dms, chats):
    ln, plate, ro = _a_customer(chats)
    _, s = dms.verify_customer(ln, plate=plate)
    res = dms.get_repair_status(s, ro)
    assert res.ok and res.data["ro_number"] == ro


def test_recall_matches_model_and_year(dms, chats):
    ln, plate, _ = _a_customer(chats)  # 2021 Halden is in campaign NM-24R01
    _, s = dms.verify_customer(ln, plate=plate)
    ids = [r["campaign_id"] for r in dms.check_recalls(s).data["open_recalls"]]
    assert "NM-24R01" in ids


def test_warranty_status_gives_facts_not_a_decision(dms, chats):
    ln, plate, _ = _a_customer(chats)
    _, s = dms.verify_customer(ln, plate=plate)
    res = dms.get_warranty_status(s)
    assert res.ok and res.data["decision_required_by"] == "warranty_desk"
    assert {c["coverage"] for c in res.data["coverages"]} == {"basic", "powertrain", "corrosion"}


def test_claim_is_drafted_not_approved(dms, chats):
    ln, plate, _ = _a_customer(chats)
    _, s = dms.verify_customer(ln, plate=plate)
    res = dms.draft_warranty_claim(s, "yellow traction control light flashing")
    assert res.ok and res.data["status"] == "submitted_for_review"


def test_booking_takes_slot_and_double_booking_conflicts(dms, chats):
    ln, plate, _ = _a_customer(chats)
    _, s = dms.verify_customer(ln, plate=plate)
    slot = dms.list_slots("Oakville").data["slots"][0]["slot_id"]
    assert dms.book_slot(s, slot).ok
    assert dms.book_slot(s, slot).error == ToolError.CONFLICT


# --- failure handling --------------------------------------------------------
def test_forced_timeout_returns_result_not_exception(chats):
    dms = DealerSystem(force_failure=ToolError.TIMEOUT)
    ln, plate, _ = _a_customer(chats)
    res, s = dms.verify_customer(ln, plate=plate)
    assert not res.ok and res.error == ToolError.TIMEOUT and s is None


def test_random_failures_follow_failure_rate(chats):
    dms = DealerSystem(failure_rate=0.5, seed=3)
    results = [dms.list_slots("Oakville").ok for _ in range(200)]
    assert 60 < results.count(False) < 140
