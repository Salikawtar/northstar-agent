"""Fine-tuned router tests. Offline and CPU only: a tiny random model stands in for XLM-R.

Skipped when torch or transformers are not installed (they are only needed for
Phase 5: pip install -r requirements-finetune.txt).
"""
import json

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from northstar.contracts import RequestType, RouterOutput  # noqa: E402


@pytest.fixture(scope="module")
def tiny_model(tmp_path_factory):
    """A 2-layer XLM-R shaped model with random weights (about 8M numbers, trains in seconds)."""
    folder = tmp_path_factory.mktemp("tiny")
    try:
        tok = transformers.AutoTokenizer.from_pretrained("xlm-roberta-base")
        cfg = transformers.AutoConfig.from_pretrained("xlm-roberta-base", hidden_size=32, num_hidden_layers=2,
                                                      num_attention_heads=2, intermediate_size=64)
    except OSError:
        pytest.skip("xlm-roberta-base tokenizer not available offline")
    transformers.AutoModel.from_config(cfg).save_pretrained(folder)
    tok.save_pretrained(folder)
    return str(folder)


def test_labels_follow_the_contract():
    from northstar.finetune.model import REQUEST_TYPES
    assert REQUEST_TYPES == [t.value for t in RequestType]


def test_model_input_is_the_prompted_router_input():
    # Same text for all three routers, so the comparison is fair.
    from northstar.agent.router import format_conversation, turns_from_row
    from northstar.finetune.train_router import split_frames
    d = split_frames()
    row = d["train"].iloc[0]
    assert row["text"] == format_conversation(turns_from_row(row))
    assert {k: len(v) for k, v in d.items()} == {"train": 130, "validation": 30, "test": 40}


def test_selection_never_reads_the_test_split(tiny_model, monkeypatch, tmp_path):
    from northstar.finetune import train_router as tr
    data = tr.split_frames()
    poisoned = {**data, "test": data["test"].assign(text=None)}   # any use of test text would crash
    monkeypatch.setattr(tr, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(tr, "SELECT_SEEDS", [1])
    args = type("A", (), dict(models=[tiny_model], lrs=[2e-5], quiet=True))()
    tr.run_select(args, poisoned, torch.device("cpu"), dict(tr.DEFAULTS, epochs=1))
    summary = json.loads((tmp_path / "selection_summary.json").read_text())
    assert summary["chosen_model"] == tiny_model and "test not touched" in summary["split_used"]


def test_threshold_favours_recall():
    from northstar.finetune.train_router import choose_threshold
    frame = pd.DataFrame({"esc_label": [1, 1, 1, 0, 0, 0]})
    probs = np.array([0.9, 0.35, 0.3, 0.32, 0.1, 0.05])
    assert choose_threshold(frame, probs) <= 0.3          # catching every escalation beats a few false alarms


def test_checkpoint_round_trip_gives_valid_router_output(tiny_model, tmp_path):
    from northstar.finetune.model import RouterClassifier, save_checkpoint
    from northstar.finetune.predict import FinetunedRouter
    save_checkpoint(RouterClassifier(tiny_model), tmp_path, dict(threshold=0.0, max_length=64))
    router = FinetunedRouter(tmp_path)
    res = router.route([("customer", "my brakes failed on the 401"), ("agent", "Are you safe?"),
                        ("customer", "yes, on the shoulder")])
    out = res.output
    assert isinstance(out, RouterOutput) and 0 <= out.confidence <= 1
    assert out.needs_escalation and out.escalation_reason.value != "none"   # threshold 0: always escalates, with a reason
    assert res.cost_usd == 0 and res.latency_ms > 0


def test_missing_checkpoint_says_how_to_train(tmp_path):
    from northstar.finetune.predict import FinetunedRouter
    with pytest.raises(FileNotFoundError, match="train_router"):
        FinetunedRouter(tmp_path / "nothing_here")


def _fake_run(n=40, wrong_every=None, cost=0.0, latency=5.0):
    from northstar.data import load_conversations
    test = load_conversations("test").head(n)
    pred = test.request_type.copy()
    if wrong_every:
        pred.iloc[::wrong_every] = "out_of_scope"
    return pd.DataFrame(dict(id=test.id, gold_type=test.request_type, pred_type=pred,
                             gold_escalation=test.needs_escalation.astype(bool), pred_escalation=test.needs_escalation.astype(bool),
                             gold_language=test.language, pred_language=test.language, difficulty=test.difficulty,
                             adversarial_type=test.adversarial_type.fillna(""), latency_ms=latency, cost_usd=cost, confidence=0.9,
                             type_correct=test.request_type == pred))


def test_comparison_uses_one_scoring_function_for_all(monkeypatch, tmp_path):
    from northstar.finetune import compare
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(compare, "HERE", tmp_path)
    monkeypatch.setattr(compare, "RUNS", runs)
    monkeypatch.setattr(compare, "ROUTERS", {"A": "router_a", "B": "router_b", "C": "router_c"})
    for name, kw in {"a": dict(wrong_every=4), "b": dict(wrong_every=10, cost=0.0004, latency=2000),
                     "c": dict(cost=0.005, latency=900)}.items():
        _fake_run(**kw).to_csv(runs / f"router_{name}_test.csv", index=False)
        (runs / f"router_{name}_test.json").write_text(json.dumps({"model": name}))
    table = compare.build().set_index("router")
    assert table.loc["A", "type_accuracy"] == pytest.approx(0.75)
    assert table.loc["C", "type_accuracy"] == 1.0 and table.loc["C", "cost_usd_per_1000_chats"] == pytest.approx(5.0)
    stats = json.loads((tmp_path / "comparison_stats.json").read_text())
    assert stats["paired_tests_type_accuracy"]["A vs C"]["only_second_right"] == 10
    assert (tmp_path / "comparison_per_class.csv").exists() and (tmp_path / "comparison_by_slice.csv").exists()


def test_datasize_subsets_keep_every_type_and_never_touch_test(tiny_model, monkeypatch, tmp_path):
    from northstar.finetune import train_router as tr
    data = tr.split_frames()
    for frac in tr.DATASIZE_FRACTIONS:
        sub = tr.stratified_subset(data["train"], frac, seed=1)
        assert sub.request_type.nunique() == 10 and len(sub) <= len(data["train"])
    poisoned = {**data, "test": data["test"].assign(text=None)}
    monkeypatch.setattr(tr, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(tr, "DATASIZE_FRACTIONS", [0.25, 1.0])
    monkeypatch.setattr(tr, "DATASIZE_SEEDS", [1])
    args = type("A", (), dict(model=tiny_model, lr=2e-5, quiet=True))()
    tr.run_datasize(args, poisoned, torch.device("cpu"), dict(tr.DEFAULTS, epochs=1))
    runs = pd.read_csv(tmp_path / "datasize_runs.csv")
    assert list(runs.train_chats) == [33, 130]


def test_datasize_extrapolation(monkeypatch, tmp_path):
    from northstar.finetune import datasize
    # Accuracy rises 5 points per doubling; a 10-point gap needs 2 more doublings: 128 * 4 = 512 chats.
    rows = [dict(train_chats=n, seed=s, val_type_accuracy=0.5 + 0.05 * np.log2(n / 32), val_macro_f1=0.5)
            for n in (32, 64, 96, 128) for s in (1, 2, 3)]
    monkeypatch.setattr(datasize, "HERE", tmp_path)
    pd.DataFrame(rows).to_csv(tmp_path / "datasize_runs.csv", index=False)
    s = datasize.build(haiku_val=0.8, gap=0.10)
    assert s["gain_per_doubling_points"] == pytest.approx(5.0)
    assert abs(s["chats_to_close_test_gap_if_trend_holds"] - 510) <= 10


def test_breakeven_is_fixed_cost_over_cost_per_chat(monkeypatch, tmp_path):
    from northstar.finetune import breakeven
    pd.DataFrame([{"router": breakeven.FT, "latency_ms_median": 250, "cost_usd_per_chat": 0.0},
                  {"router": breakeven.SMALL, "latency_ms_median": 2000, "cost_usd_per_chat": 0.0005},
                  {"router": breakeven.LARGE, "latency_ms_median": 1000, "cost_usd_per_chat": 0.005}]
                 ).to_csv(tmp_path / "comparison_table.csv", index=False)
    (tmp_path / "training_log.json").write_text(json.dumps({"cost_usd_all_runs": 0.0}))
    monkeypatch.setattr(breakeven, "HERE", tmp_path)
    hosting = dict(server="test", usd_per_hour=0.1, usd_per_hour_committed=0.05, hours_per_month=700,
                   servers=1, max_utilisation=0.5, retrains_per_year=4)
    monkeypatch.setattr(breakeven, "settings", lambda: {"finetuned_router_hosting": hosting})
    scen, s = breakeven.build()
    assert s["base_case"]["monthly_fixed_usd"] == 70.0
    assert s["base_case"]["vs_haiku_chats_per_month"] == 140_000      # 70 / 0.0005
    assert scen.set_index("chats_per_month").loc[1_000_000, "cheapest"] == "finetuned"


def test_lora_trains_far_fewer_weights_and_never_touches_test(tiny_model, monkeypatch, tmp_path):
    pytest.importorskip("peft")
    from northstar.finetune import train_router as tr
    from northstar.finetune.model import RouterClassifier, trainable_parameters
    full, lora = RouterClassifier(tiny_model), RouterClassifier(tiny_model, lora=tr.LORA)
    assert trainable_parameters(lora) < trainable_parameters(full) / 10
    data = tr.split_frames()
    poisoned = {**data, "test": data["test"].assign(text=None)}
    monkeypatch.setattr(tr, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(tr, "LORA_LRS", [1e-3])
    monkeypatch.setattr(tr, "LORA_SEEDS", [1])
    args = type("A", (), dict(model=tiny_model, quiet=True))()
    tr.run_lora(args, poisoned, torch.device("cpu"), dict(tr.DEFAULTS, epochs=1))
    s = json.loads((tmp_path / "lora_summary.json").read_text())
    assert s["lora_best_lr"] == 1e-3 and "test not touched" in s["split_used"]
