"""The final run's scoring and recordings, on practice chats with made-up model scores (no training, no test chat)."""
import numpy as np

from northstar.finetune.study import final_run as F
from northstar.finetune.study import protocol as P
from northstar.finetune.study import router_options as O
from northstar.finetune.study import routing as R

RECORDED_ROUTER_NEEDS = {"id", "pred_type", "pred_escalation", "pred_reason", "pred_language", "confidence", "latency_ms", "input_tokens"}


def test_confidence_map_moves_the_own_line_onto_the_team_line():
    c = np.linspace(0.01, 0.99, 99)
    m = F.report_confidence(c, 0.40)
    assert ((c < 0.40) == (m < R.FLOOR)).all() and np.all(np.diff(m) > 0)
    assert np.allclose(F.report_confidence(c, R.FLOOR), c)


def test_scoring_and_recording_on_practice_chats(tmp_path):
    held = P.pool(P.load_all()).iloc[:30].assign(dataset="test").reset_index(drop=True)
    rng = np.random.default_rng(0)
    paths = []
    for seed in (101, 102):
        p = tmp_path / f"seed{seed}.npz"
        np.savez_compressed(p, ids=held["id"].values.astype(str), dataset=held["dataset"].values.astype(str), seed=seed,
                            seconds=1.0, logits_type=rng.normal(size=(30, 10)), logits_escalation=rng.normal(size=30),
                            logits_attack=rng.normal(size=30))
        paths.append(p)
    combined, per_seed, seeds, _ = F.tuned_answers(paths, held, 0.10, 0.05)
    assert seeds == [101, 102] and len(per_seed) == 2 and len(combined) == 30
    lang = P.input_text(held, "first_message").map(R.language_rule).values
    row, routed = F.score_router(held, O.option_attack_head(combined), lang, 0.40, n_boot=50)
    assert row["chats"] == 30 and row["language_accuracy"] == 1.0 and len(routed) == 30
    rec = F.recording(held, combined, lang, 0.40, 250.0)
    assert RECORDED_ROUTER_NEEDS <= set(rec.columns)
    assert set(rec.loc[rec["pred_escalation"], "pred_reason"]) <= set(P.REASONS) - {"none"}
    assert (rec.loc[~rec["pred_escalation"], "pred_reason"] == "none").all()
