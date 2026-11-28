"""The reported pool numbers come back from the saved runs and answers in the repo (no GPU, no key).

If one of these fails, a number in the lab notes, notebook 05 or the scorecard no longer matches the code."""
import numpy as np
import pandas as pd
import pytest

from northstar.finetune.study import baselines as B
from northstar.finetune.study import cv_analysis as A
from northstar.finetune.study import protocol as P
from northstar.finetune.study import router_options as O

ROOT = P.STUDY / "results"


@pytest.fixture(scope="module")
def pool():
    return P.pool(P.load_all())


def tuned(pool, folder, variant, heads=("type", "escalation")):
    oof = A.assemble(A.load_variant(folder, variant), pool, heads)
    e = A.pick_epoch(A.epoch_curves(oof, pool))[0]
    att = O.choose_cutoff(oof, pool, e, "attack", "attack_label")[0] if "attack" in heads else None
    return e, O.tuned_answers(oof, pool, e, O.choose_cutoff(oof, pool, e)[0], att)


def test_notebook_02_baseline(pool):
    oof = A.assemble(A.load_variant(ROOT / "cv_old_recipe", "first_message"), pool)
    s = A.summary_at_epoch(oof, pool, 30)
    assert round(s["per_seed"]["type_accuracy"].mean(), 3) == 0.719
    assert round(s["ensemble_type"]["accuracy"], 3) == 0.756


def test_haiku_alone_first_message(pool):
    h = O.combine_llm(B.load_preds(ROOT / "step04" / "preds", "haiku", "first_message", pool))
    s, _ = O.score(pool, O.option_llm_alone(h))
    assert (s["right_team"], s["attacks_right_team"], s["missed"], s["extra_handoffs"]) == (65, 30, 3, 9)
    assert round(s["handled_right"], 3) == 0.900


def test_jev_same_information_first_message(pool):
    j = O.combine_llm(B.load_preds(ROOT / "step04b" / "preds", "jev2", "first_message", pool))
    s, _ = O.score(pool, O.option_llm_alone(j))
    assert (s["attacks_right_team"], round(s["handled_right"], 3)) == (31, 0.900)


def test_her_rule_sends_few_attacks_to_the_right_team(pool):
    _, t = tuned(pool, ROOT / "cv_old_recipe", "first_message")
    s, _ = O.score(pool, O.option_her_rule(t))
    assert (s["right_team"], s["attacks_right_team"], round(s["handled_right"], 3)) == (38, 6, 0.544)


def test_balanced_setup_and_its_unsure_line(pool):
    e, t = tuned(pool, ROOT / "cv_step03c" / "lora_attack", "first_message", ("type", "escalation", "attack"))
    ans = O.option_attack_head(t)
    line, _ = O.choose_floor(pool, ans)
    s, _ = O.score(pool, ans, line)
    assert e == 60 and line == 0.40
    assert (s["missed"], s["right_team"], s["attacks_right_team"], s["extra_handoffs"]) == (6, 59, 25, 15)
    assert round(s["handled_right"], 3) == 0.794


def test_frozen_settings_match_the_pool_results():
    import json
    s = json.loads((P.STUDY / "config" / "final_settings.json").read_text(encoding="utf-8"))["fine_tuned"]
    cand = pd.read_csv(ROOT / "step05" / "tuned_candidates.csv")
    lora = cand[(cand.model == "LoRA 60 epochs + attack") & (cand.input == "first_message")].iloc[0]
    full = cand[(cand.model == "full fine-tuning + attack") & (cand.input == "first_message")].iloc[0]
    assert (s["balanced"]["training"]["epochs"], s["balanced"]["escalation_cutoff"], s["balanced"]["attack_cutoff"]) == \
           (int(lora.epoch), lora.esc_cutoff_probability, lora.attack_cutoff_probability)
    assert (s["safest"]["training"]["epochs"], s["safest"]["escalation_cutoff"], s["safest"]["attack_cutoff"]) == \
           (int(full.epoch), full.esc_cutoff_probability, full.attack_cutoff_probability)
