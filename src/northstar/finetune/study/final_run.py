"""The final run: train the two frozen fine-tuned setups on all 160 pool chats, then score the locked test chats and
the fresh chats ONCE, together with Haiku, Sonnet and Jev, all by the same code.

Every choice comes from config/final_settings.json, written before any test or fresh chat was opened. Training
never sees the scored chats' answers (they are replaced by zeros), and the scored chats are read only after the last
epoch, so no epoch, cut-off or line can be chosen on them.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from northstar.finetune.study import metrics as M
from northstar.finetune.study import protocol as P
from northstar.finetune.study import router_options as O
from northstar.finetune.study import routing as R

SETTINGS_PATH = P.STUDY / "config" / "final_settings.json"
HEAD_COLUMN = {"type": "type_label", "escalation": "escalation_label", "language": "language_label", "attack": "attack_label"}


def load_settings() -> dict:
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def train_config(training: dict):
    from northstar.finetune.study.train_cv import TrainConfig
    kw = dict(training)
    kw["heads"] = tuple(kw["heads"])
    return TrainConfig(**kw)


def _logit(p: float) -> float:
    return float(np.log(p / (1 - p)))


# ---------------------------------------------------------------------------------------------------------
# Training on all 160 pool chats, scoring the held-out chats after the last epoch
# ---------------------------------------------------------------------------------------------------------
def train_and_score(cfg, variant: str, train_df: pd.DataFrame, score_df: pd.DataFrame, seeds, out_dir,
                    keep_seed=None, save_trained_weights: bool = False, tokenizer=None, device=None, verbose: bool = True):
    """One model per seed, trained on `train_df`, scored on `score_df` after its last epoch. Saves one small file of
    scores per seed (and, if asked, the trained weights: for LoRA only the small add-ons and the answer heads).
    Returns (saved score files, the model trained with `keep_seed` or None)."""
    import torch
    from northstar.finetune.study.model import BINARY_HEADS
    from northstar.finetune.study.train_cv import run_one

    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if tokenizer is None:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(cfg.model_name)
    texts = list(P.input_text(train_df, variant)) + list(P.input_text(score_df, variant))
    token_ids = tokenizer(texts, truncation=True, max_length=cfg.max_length)["input_ids"]
    n_train, n_score = len(train_df), len(score_df)
    labels = {}
    for h in cfg.heads:      # the scored chats' answers are never given to training: zeros stand in for them
        y = np.concatenate([train_df[HEAD_COLUMN[h]].values.astype(float), np.zeros(n_score)])
        labels[h] = torch.tensor(y, dtype=torch.float32 if h in BINARY_HEADS else torch.long).to(device)
    train_idx, score_idx = np.arange(n_train), np.arange(n_train, n_train + n_score)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    kept, paths = None, []
    for seed in seeds:
        path = out / f"seed{seed}.npz"
        weights = out / f"seed{seed}_trained_weights.pt"
        need_model = seed == keep_seed or (save_trained_weights and not weights.exists())
        if path.exists() and not need_model:
            paths.append(path)
            continue
        t0 = time.time()
        hist = run_one(cfg, token_ids, labels, train_idx, score_idx, seed, tokenizer.pad_token_id, device,
                       epochs=cfg.epochs, score_every_epoch=False, return_model=need_model)
        model = hist.pop("model", None)
        seconds = time.time() - t0
        np.savez_compressed(path, ids=score_df["id"].values.astype(str), dataset=score_df["dataset"].values.astype(str),
                            seed=seed, seconds=seconds, train_loss=hist["train_loss"], n_trainable=hist["n_trainable"],
                            **{f"logits_{h}": hist[f"logits_{h}"][-1] for h in cfg.heads})
        if save_trained_weights and model is not None:
            trained = {n for n, p_ in model.named_parameters() if p_.requires_grad}
            torch.save({k: v.detach().cpu() for k, v in model.state_dict().items() if k in trained}, weights)
        if seed == keep_seed:
            kept = model
        del model
        paths.append(path)
        if verbose:
            print(f"  seed {seed}: trained on {n_train} chats in {seconds:.0f}s, scored {n_score} held-out chats once", flush=True)
    return paths, kept


def tuned_answers(paths, score_df: pd.DataFrame, esc_cutoff: float, attack_cutoff: float):
    """The combined answer (average of the seeds' scores) and each seed's own answer, aligned to `score_df`."""
    runs = [dict(np.load(p, allow_pickle=False)) for p in paths]
    for r in runs:
        assert list(r["ids"]) == list(score_df["id"].astype(str)), "score files do not match the scored chats"

    def answers(type_logits, esc_logits, attack_logits):
        return pd.DataFrame({"type": [P.REQUEST_TYPES[i] for i in type_logits.argmax(-1)],
                             "esc": esc_logits > _logit(esc_cutoff),
                             "confidence": R.softmax_confidence(type_logits),
                             "attack": attack_logits > _logit(attack_cutoff)})
    per_seed = [answers(r["logits_type"], r["logits_escalation"], r["logits_attack"]) for r in runs]
    combined = answers(np.mean([r["logits_type"] for r in runs], axis=0), np.mean([r["logits_escalation"] for r in runs], axis=0),
                       np.mean([r["logits_attack"] for r in runs], axis=0))
    return combined, per_seed, [int(r["seed"]) for r in runs], [float(r["seconds"]) for r in runs]


def cpu_latency(model, tokenizer, texts, max_length: int = 320, threads: int = 2) -> dict:
    """Seconds per chat for one model on a CPU with `threads` cores, one chat at a time (as one customer's
    chat is routed); the first chat is a warm-up and is left out."""
    import torch
    model = model.to("cpu").float().eval()
    old = torch.get_num_threads()
    torch.set_num_threads(threads)
    times = []
    with torch.no_grad():
        for i, text in enumerate(texts):
            t0 = time.perf_counter()
            enc = tokenizer(text, truncation=True, max_length=max_length, return_tensors="pt")
            model(enc["input_ids"], enc["attention_mask"])
            if i > 0:
                times.append(time.perf_counter() - t0)
    torch.set_num_threads(old)
    return dict(chats=len(times), median_s=float(np.median(times)), p90_s=float(np.quantile(times, 0.9)), threads=threads)


# ---------------------------------------------------------------------------------------------------------
# Scoring, the same way for every router
# ---------------------------------------------------------------------------------------------------------
def score_router(df: pd.DataFrame, ans: pd.DataFrame, language_pred, floor: float = R.FLOOR, n_boot: int = 2000):
    """One row of the final table and the per-chat outcome, for one router on one set of chats."""
    df, ans = df.reset_index(drop=True), ans.reset_index(drop=True)
    s, routed = O.score(df, ans, floor)
    ok = ans["type"].values == df["request_type"].values
    en, fr = (df["language"] == "en").values, (df["language"] == "fr").values
    gold = df["escalation_label"].values == 1
    esc = ans["esc"].values.astype(bool)
    groups = df["customer_id"].values
    hr = routed["handled_right"].values.astype(float)
    t_lo, t_hi = M.cluster_bootstrap(lambda idx: ok[idx].mean(), groups, n_boot=n_boot)
    h_lo, h_hi = M.cluster_bootstrap(lambda idx: hr[idx].mean(), groups, n_boot=n_boot)
    row = dict(chats=len(df), type_accuracy=ok.mean(), type_ci_low=t_lo, type_ci_high=t_hi,
               type_accuracy_en=ok[en].mean() if en.any() else np.nan, type_accuracy_fr=ok[fr].mean() if fr.any() else np.nan,
               language_accuracy=float((np.asarray(language_pred) == df["language"].values).mean()),
               needs_person=int(gold.sum()), caught=int((esc & gold).sum()), false_alarms=int((esc & ~gold).sum()),
               missed=s["missed"], right_team=s["right_team"], wrong_team=s["wrong_team"],
               attacks=s["attacks"], attacks_right_team=s["attacks_right_team"],
               extra_handoffs=s["extra_handoffs"], kept_wrong_desk=s["kept_wrong_desk"],
               handled_right=hr.mean(), handled_ci_low=h_lo, handled_ci_high=h_hi, handled_right_rules=s["handled_right_rules"],
               llm_share=s["llm_share"], usd_per_1000=s["usd_per_1000"])
    return row, routed


def paired_vs(reference: np.ndarray, other: np.ndarray) -> dict:
    t = M.mcnemar_exact(other.astype(bool), reference.astype(bool))
    return dict(only_router_right=t["only_a_right"], only_reference_right=t["only_b_right"], p_value=t["p_value"])


# ---------------------------------------------------------------------------------------------------------
# A recording the team's harness can replay (evaluation/setups.py, RecordedRouter)
# ---------------------------------------------------------------------------------------------------------
def report_confidence(confidence, own_line: float, team_line: float = R.FLOOR):
    """The tuned router's confidence, rescaled so that its own unsure line lands on the team's 0.55: the team's
    pipeline then hands over exactly the chats the tuned router's own line would. Order is kept (a calibration map)."""
    c = np.asarray(confidence, float)
    if abs(own_line - team_line) < 1e-9:
        return c
    low = c < own_line
    return np.where(low, team_line * c / own_line, team_line + (1 - team_line) * (c - own_line) / (1 - own_line))


def recording(df: pd.DataFrame, ans: pd.DataFrame, language_pred, own_line: float, latency_ms: float, tokenizer=None) -> pd.DataFrame:
    """Rows in the format of the team's router recordings (id, pred_type, pred_escalation, pred_reason,
    pred_language, confidence, latency_ms, input_tokens, ...), for the team's end-to-end harness."""
    df, ans = df.reset_index(drop=True), ans.reset_index(drop=True)
    esc = ans["esc"].values | ans["attack"].values
    reasons = [R.reason_from_type(t, a) if e else "none" for t, e, a in zip(ans["type"], esc, ans["attack"])]
    tokens = ([len(tokenizer(x)["input_ids"]) for x in P.input_text(df, "first_message")] if tokenizer is not None
              else [0] * len(df))
    return pd.DataFrame({"id": df["id"], "gold_type": df["request_type"], "pred_type": ans["type"],
                         "gold_escalation": df["needs_escalation"].astype(bool), "pred_escalation": esc,
                         "pred_reason": reasons, "gold_language": df["language"], "pred_language": language_pred,
                         "secondary": "", "confidence": np.round(report_confidence(ans["confidence"], own_line), 4),
                         "difficulty": df.get("difficulty", ""), "adversarial_type": df["adversarial_type"].fillna(""),
                         "latency_ms": round(latency_ms, 1), "cost_usd": 0.0, "input_tokens": tokens, "output_tokens": 0,
                         "fallback": False, "error": "", "type_correct": ans["type"].values == df["request_type"].values})


def llm_recording(held: pd.DataFrame, preds_dir, model_key: str, variant: str, latency_ms: float) -> pd.DataFrame:
    """The same recording format for a language-model router (for example Jev with the same information), from its
    saved answers on the held-out chats, so the team's harness can run the whole agent with it as the router."""
    from northstar.finetune.study import baselines as B
    reps = B.load_preds(preds_dir, model_key, variant, held)
    llm = O.combine_llm(reps)
    lang = np.where(np.mean([(r["language"] == "fr").values for r in reps], axis=0) > 0.5, "fr", "en")
    esc = llm["esc"].values.astype(bool)
    reasons = [(r if r != "none" else "customer_request") if e else "none" for r, e in zip(llm["reason"], esc)]
    return pd.DataFrame({"id": held["id"].values, "gold_type": held["request_type"].values, "pred_type": llm["type"].values,
                         "gold_escalation": held["needs_escalation"].astype(bool).values, "pred_escalation": esc,
                         "pred_reason": reasons, "gold_language": held["language"].values, "pred_language": lang,
                         "secondary": "", "confidence": np.round(llm["confidence"].values, 4),
                         "difficulty": held.get("difficulty", ""), "adversarial_type": held["adversarial_type"].fillna("").values,
                         "latency_ms": round(latency_ms, 1), "cost_usd": llm["cost_usd"].values, "input_tokens": 0, "output_tokens": 0,
                         "fallback": False, "error": "", "type_correct": llm["type"].values == held["request_type"].values})
