"""Tests for the data-generation pipeline (criterion 1 and criterion 3: the generator is in the codebase and reproducible).

The recorded generation run in data/source/generation/ is replayed with no key and no network, and the result is
compared with data/conversations/conversations.csv: the 200 ids, the customers, the request types and the Faker
identifiers must be the same. The text and the escalation labels are allowed to differ, because the team edited them
after generation; every such edit is in the QC_log sheet of the review workbook.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from northstar.data import load_conversations
from northstar.datagen import build_redteam, export
from northstar.datagen import pipeline as sp

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "source" / "generation"


@pytest.fixture(scope="module")
def manifest():
    return json.load(open(GEN / "run_manifest.json", encoding="utf-8"))


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    out = tmp_path_factory.mktemp("datagen_replay")
    cfg = sp.Cfg()
    cfg.seed, cfg.out_dir, cfg.cache_dir = 42, str(out), str(out / "cache")
    cfg.jobs_file = str(GEN / "jobs_designed.jsonl")
    client = sp.LLMClient(generations=sp.load_generations(str(GEN / "generations_v3_conv.jsonl")),
                          generator_name="recorded run", cache_dir=str(out / "cache"))
    res = sp.run_pipeline(cfg, client, verbose=False)
    res["csv"] = export.load_run(out)
    return res


@pytest.fixture(scope="module")
def chats():
    return load_conversations().sort_values("id").reset_index(drop=True)


def test_prompt_in_code_is_the_prompt_that_made_the_data(manifest):
    # An edited prompt without a version bump would still be caught here.
    assert sp.prompt_sha256() == manifest["prompt_sha256"]
    assert sp.PROMPT_VERSION == manifest["prompt_version"]


def test_replay_keeps_200_and_logs_15_rejections_with_reasons(replay, manifest):
    s = replay["summary"]
    assert (s["n_generated"], s["n_kept"], s["n_rejected"]) == (215, 200, 15)
    assert s["reject_reasons"] == manifest["summary"]["reject_reasons"]
    assert replay["rejected"]["qc_reasons"].apply(len).min() >= 1          # every rejection carries its reason


def test_replay_matches_the_dataset_ids_customers_and_request_types(replay, chats):
    gen = replay["csv"]
    assert gen["id"].tolist() == chats["id"].tolist()
    m = gen.merge(chats, on="id", suffixes=("_gen", "_data"))
    for col in ("customer_id", "request_type", "difficulty", "customer_type", "language"):
        assert (m[f"{col}_gen"].astype(str) == m[f"{col}_data"].astype(str)).all(), col


def test_replay_faker_identifiers_match_the_dataset(replay, chats):
    # Same customer seed -> same name, VIN, plate and repair order, so the mock dealer system built from the
    # dataset also matches the generation run.
    m = replay["csv"].merge(chats, on="id", suffixes=("_gen", "_data"))
    for col in ("faker_customer_name", "faker_vin", "faker_plate", "faker_ro_number"):
        assert (m[f"{col}_gen"].astype(str) == m[f"{col}_data"].astype(str)).all(), col


def test_coverage_matrix_is_met_by_the_kept_rows(replay):
    kept = replay["kept"]
    assert kept["intent"].value_counts().to_dict() == {i: 20 for i in sp.INTENTS}
    assert kept.groupby("intent")["difficulty"].value_counts().min() >= 4   # 10 easy / 6 hard / 4 adversarial per intent
    assert kept["lang"].value_counts().to_dict() == {"en": 130, "fr": 70}
    assert set(kept["adversarial_type"].dropna().value_counts()) == {8}


def test_replay_split_is_grouped_by_customer_with_no_near_copies_across(replay):
    # The fold itself depends on the scikit-learn version (see datagen/split.py), so the replay is checked
    # for the protections, not for the exact 160 / 40 cut; the recorded cut is checked in test_data_quality.
    check = replay["split_check"]
    assert abs(len(replay["test"]) - 40) <= 2 and len(replay["train"]) + len(replay["test"]) == 200
    assert check["customers_in_both_splits"] == 0 and check["overlap_zero"]


def test_every_faker_field_in_the_dataset_has_a_valid_format(chats):
    # The formats the pipeline enforces (Ontario 555-01XX phones, example.com e-mails, 17-character VINs, CXXX 000 plates).
    import re
    fmt = sp.SLOT_FORMATS
    for col, slot in (("faker_email", "email"), ("faker_phone", "phone"), ("faker_vin", "vin"), ("faker_plate", "plate"), ("faker_ro_number", "ro_number")):
        pattern = re.compile(fmt[slot][1])
        bad = [v for v in chats[col].astype(str) if not pattern.match(v)]
        assert not bad, (col, bad[:3])


def test_redteam_matrix_in_code_is_the_matrix_behind_the_redteam_set():
    jobs = build_redteam.design_jobs()
    rt = pd.read_csv(ROOT / "data" / "redteam" / "redteam_75.csv")
    assert jobs["id"].tolist() == sorted(rt["id"].tolist())
    m = jobs.merge(rt, on="id")
    assert (m["adversarial_type"] == m["attack_type"]).all()
    assert (m["group"] == m["customer_id"]).all()
    assert (m["lang"] == m["language"]).all()


def test_replay_does_not_depend_on_what_is_installed(monkeypatch):
    # langdetect misreads the 11-character chat v3_0109 ("service sat"); the default check must not use it.
    import sys
    import types
    fake = types.ModuleType("langdetect")
    fake.detect = lambda text: "so"                 # a detector that gets everything wrong
    fake.DetectorFactory = types.SimpleNamespace(seed=0)
    monkeypatch.setitem(sys.modules, "langdetect", fake)
    assert sp._detect_lang("service sat. am. plate CDBF 609") != "so"
    assert sp._detect_lang("service sat", "langdetect") == "so"   # only when asked for explicitly
