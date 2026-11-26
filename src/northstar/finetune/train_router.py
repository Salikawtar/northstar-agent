"""Train the fine-tuned router (Phase 5). Every choice is made on validation; test is scored at the end.

Two steps, run in order (both need a GPU to be quick; about 45 minutes in total on a free Kaggle T4):

    # 1. Choose the base model and the learning rate. Uses the 30 validation chats only.
    python -m northstar.finetune.train_router select

    # 2. Train the chosen settings with 5 seeds, keep the seed with the best validation
    #    score as the router, and only then score all 5 seeds once on the 40 test chats
    #    (to show how much a single training run can vary).
    python -m northstar.finetune.train_router final --out models/finetuned_router

    # 3. (Optional) How accuracy grows with training data: train on 25%, 50%, 75%
    #    and 100% of the training chats, 3 seeds each, scored on validation only.
    python -m northstar.finetune.train_router datasize

    # 4. (Optional) Training method: LoRA (frozen encoder, small trained add-ons) against full
    #    fine-tuning, same base model and data, 3 seeds per learning rate, validation only.
    python -m northstar.finetune.train_router lora

Then the official comparison row comes from the same script that scores the prompted routers:

    python -m northstar.agent.router --split test --model finetuned

Why the test chats are kept out of steps 1 and 2: with only 40 test chats, picking a model
or a learning rate on them would make the reported number look better than it really is.

Input text: the same three-turn conversation the prompted router reads (customer, agent,
customer), built by the same function, so the three routers are compared on the same input.

No API key is used here. Training runs on local data only.
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import f1_score, fbeta_score, precision_score, recall_score
from torch.utils.data import DataLoader
from transformers import AutoTokenizer, get_linear_schedule_with_warmup

from northstar.agent.router import format_conversation, turns_from_row
from northstar.data import load_conversations
from northstar.finetune.model import LANGUAGES, REQUEST_TYPES, RouterClassifier, save_checkpoint, trainable_parameters

RESULTS_DIR = Path(__file__).parent / "results"

# Step 1 search space. Two seeds per setting, because one run on 130 chats is partly luck.
CANDIDATE_MODELS = ["xlm-roberta-base", "distilbert-base-multilingual-cased", "microsoft/mdeberta-v3-base"]
CANDIDATE_LRS = [1e-5, 2e-5, 3e-5]
SELECT_SEEDS = [1, 2]
FINAL_SEEDS = [1, 2, 3, 4, 5]
DATASIZE_FRACTIONS = [0.25, 0.5, 0.75, 1.0]
DATASIZE_SEEDS = [1, 2, 3]
LORA = dict(r=16, lora_alpha=32, lora_dropout=0.1, target_modules=["query", "value"])
LORA_LRS = [3e-4, 1e-3]          # LoRA needs a higher learning rate than full fine-tuning
LORA_SEEDS = [1, 2, 3]

DEFAULTS = dict(epochs=30, patience=6, batch_size=16, max_length=320, warmup_ratio=0.1,
                weight_decay=0.01, dropout=0.2)
THRESHOLDS = [round(x, 2) for x in np.arange(0.05, 0.96, 0.05)]
GPU_USD_PER_HOUR = 0.45   # on-demand T4 on major clouds is about 0.35 to 0.53 USD per hour (Nov 2026)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def chat_text(row: pd.Series) -> str:
    """The exact text the prompted router sees (minus its instructions)."""
    return format_conversation(turns_from_row(row))


def split_frames() -> dict[str, pd.DataFrame]:
    df = load_conversations()
    bad = set(df["request_type"]) - set(REQUEST_TYPES)
    assert not bad, f"labels not in the contract: {bad}"
    df = df.assign(text=df.apply(chat_text, axis=1),
                   type_label=df["request_type"].map(REQUEST_TYPES.index),
                   esc_label=df["needs_escalation"].astype(int),
                   lang_label=df["language"].map(LANGUAGES.index))
    return {s: df[df["split"] == s].reset_index(drop=True) for s in ("train", "validation", "test")}


def make_loader(tok, frame: pd.DataFrame, batch_size: int, max_length: int, shuffle: bool, seed: int = 0):
    items = list(zip(frame["text"], frame["type_label"], frame["esc_label"], frame["lang_label"]))

    def collate(batch):
        texts, ty, es, la = zip(*batch)
        enc = tok(list(texts), padding=True, truncation=True, max_length=max_length, return_tensors="pt")
        return (enc["input_ids"], enc["attention_mask"], torch.tensor(ty), torch.tensor(es, dtype=torch.float),
                torch.tensor(la))

    g = torch.Generator().manual_seed(seed)
    return DataLoader(items, batch_size=batch_size, shuffle=shuffle, collate_fn=collate, generator=g)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------------------
# Training and scoring
# ---------------------------------------------------------------------------
def predict_probs(model, loader, device) -> dict[str, np.ndarray]:
    model.eval()
    ty, es, la = [], [], []
    with torch.no_grad():
        for ids, mask, *_ in loader:
            t, e, l = model(ids.to(device), mask.to(device))
            ty.append(torch.softmax(t.float(), -1).cpu())
            es.append(torch.sigmoid(e.float()).cpu())
            la.append(torch.softmax(l.float(), -1).cpu())
    return {"type": torch.cat(ty).numpy(), "esc": torch.cat(es).numpy(), "lang": torch.cat(la).numpy()}


def scores(frame: pd.DataFrame, probs: dict, threshold: float = 0.5) -> dict:
    pt = probs["type"].argmax(1)
    pe = (probs["esc"] >= threshold).astype(int)
    pl = probs["lang"].argmax(1)
    yt, ye, yl = frame["type_label"].values, frame["esc_label"].values, frame["lang_label"].values
    return dict(type_accuracy=float((pt == yt).mean()),
                macro_f1=float(f1_score(yt, pt, average="macro", labels=range(len(REQUEST_TYPES)), zero_division=0)),
                escalation_recall=float(recall_score(ye, pe, zero_division=0)),
                escalation_precision=float(precision_score(ye, pe, zero_division=0)),
                escalation_accuracy=float((pe == ye).mean()),
                language_accuracy=float((pl == yl).mean()))


def choose_threshold(frame: pd.DataFrame, esc_probs: np.ndarray) -> float:
    """Escalation cut-off, chosen on validation with F2 (recall counts twice as much as precision):
    missing a chat that needs a person is the worst router mistake (operating policy)."""
    y = frame["esc_label"].values
    best = max(THRESHOLDS, key=lambda t: (fbeta_score(y, (esc_probs >= t).astype(int), beta=2, zero_division=0),
                                          -abs(t - 0.5)))
    return float(best)


def train_one(model_name: str, lr: float, seed: int, data: dict, device, cfg: dict, verbose: bool = True,
              lora: dict | None = None):
    """Train on the 130 training chats; keep the epoch with the lowest validation loss."""
    set_seed(seed)
    tok = AutoTokenizer.from_pretrained(model_name)
    tr = make_loader(tok, data["train"], cfg["batch_size"], cfg["max_length"], shuffle=True, seed=seed)
    va = make_loader(tok, data["validation"], cfg["batch_size"], cfg["max_length"], shuffle=False)
    model = RouterClassifier(model_name, dropout=cfg["dropout"], lora=lora).to(device)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=cfg["weight_decay"])
    steps = len(tr) * cfg["epochs"]
    sched = get_linear_schedule_with_warmup(opt, int(cfg["warmup_ratio"] * steps), steps)
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    ce, bce = nn.CrossEntropyLoss(), nn.BCEWithLogitsLoss()

    def batch_loss(ids, mask, ty, es, la):
        with torch.autocast(device.type, dtype=torch.float16, enabled=use_amp):
            t, e, l = model(ids.to(device), mask.to(device))
        return ce(t.float(), ty.to(device)) + bce(e.float(), es.to(device)) + ce(l.float(), la.to(device))

    best = (float("inf"), None, 0)
    hist, wait, t0 = [], 0, time.time()
    for ep in range(1, cfg["epochs"] + 1):
        model.train()
        tr_loss = n = 0
        for b in tr:
            loss = batch_loss(*b)
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            tr_loss += loss.item() * len(b[0]); n += len(b[0])
        model.eval()
        with torch.no_grad():
            va_loss = sum(batch_loss(*b).item() * len(b[0]) for b in va) / len(data["validation"])
        hist.append(dict(epoch=ep, train_loss=tr_loss / n, val_loss=va_loss))
        if verbose:
            print(f"    epoch {ep:2d}  train_loss={tr_loss / n:.3f}  val_loss={va_loss:.3f}")
        if va_loss < best[0]:
            best, wait = (va_loss, {k: v.detach().clone() for k, v in model.state_dict().items()}, ep), 0
        else:
            wait += 1
            if wait >= cfg["patience"]:
                break
    if best[1] is None:
        raise RuntimeError("training diverged (validation loss was never a number)")
    model.load_state_dict(best[1])
    val_probs = predict_probs(model, va, device)
    info = dict(model=model_name, lr=lr, seed=seed, best_epoch=best[2], epochs_run=len(hist),
                val_loss=best[0], train_time_sec=round(time.time() - t0, 1),
                trainable_params=trainable_parameters(model))
    return model, tok, hist, val_probs, info


def free(device) -> None:
    import gc
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
# Step 1: choose base model and learning rate on validation
# ---------------------------------------------------------------------------
def run_select(args, data, device, cfg) -> None:
    rows = []

    def run(model_name, lr):
        for seed in SELECT_SEEDS:
            print(f"\n[select] {model_name}  lr={lr}  seed={seed}")
            try:
                model, _, _, vp, info = train_one(model_name, lr, seed, data, device, cfg, verbose=not args.quiet)
                rows.append({**info, **{f"val_{k}": v for k, v in scores(data["validation"], vp).items()}, "status": "ok"})
                del model
            except torch.cuda.OutOfMemoryError:
                rows.append(dict(model=model_name, lr=lr, seed=seed, status="out_of_memory"))
                print("    out of GPU memory: recorded and skipped")
            except (RuntimeError, OSError, ValueError) as e:     # e.g. diverged run, model that will not load
                rows.append(dict(model=model_name, lr=lr, seed=seed, status=f"failed: {str(e)[:120]}"))
                print(f"    failed: {e}; recorded and skipped")
            free(device)
            pd.DataFrame(rows).to_csv(RESULTS_DIR / "selection_runs.csv", index=False)   # saved after every run

    def ranking(frame):
        ok = frame[frame.status == "ok"]
        return (ok.groupby(["model", "lr"]).agg(val_macro_f1=("val_macro_f1", "mean"), val_loss=("val_loss", "mean"),
                                                runs=("seed", "count"))
                .sort_values(["val_macro_f1", "val_loss"], ascending=[False, True]).reset_index())

    for m in args.models:                      # 1a. base models at the usual starting learning rate
        run(m, 2e-5)
    best_model = ranking(pd.DataFrame(rows)).iloc[0]["model"]
    for lr in args.lrs:                        # 1b. learning rates for the winning base model
        if lr != 2e-5:
            run(best_model, lr)
    rank = ranking(pd.DataFrame(rows))
    rank.to_csv(RESULTS_DIR / "selection_ranking.csv", index=False)
    choice = rank.iloc[0]
    summary = dict(chosen_model=choice["model"], chosen_lr=float(choice["lr"]),
                   rule="highest mean validation macro F1 over seeds; ties broken by lower validation loss",
                   seeds=SELECT_SEEDS, split_used="validation (30 chats); test not touched",
                   excluded={r["model"]: r["status"] for r in rows if r.get("status") != "ok"})
    (RESULTS_DIR / "selection_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("\n" + rank.to_string(index=False))
    print("\nChosen:", json.dumps(summary, indent=1))


# ---------------------------------------------------------------------------
# Step 2: final training with several seeds, then test once
# ---------------------------------------------------------------------------
def run_final(args, data, device, cfg) -> None:
    sel_path = RESULTS_DIR / "selection_summary.json"
    sel = json.loads(sel_path.read_text()) if sel_path.exists() else {}
    model_name = args.model or sel.get("chosen_model") or "xlm-roberta-base"
    lr = args.lr or sel.get("chosen_lr") or 2e-5
    print(f"Final settings: {model_name}, lr={lr}, seeds={FINAL_SEEDS}")

    runs, hists, best = [], [], None
    for seed in FINAL_SEEDS:
        print(f"\n[final] seed={seed}")
        model, tok, hist, vp, info = train_one(model_name, lr, seed, data, device, cfg, verbose=not args.quiet)
        thr = choose_threshold(data["validation"], vp["esc"])
        val = scores(data["validation"], vp, thr)
        # Test probabilities are computed now but not looked at until every seed is trained
        # and the router is chosen, so nothing below depends on them.
        te = make_loader(tok, data["test"], cfg["batch_size"], cfg["max_length"], shuffle=False)
        test_probs = predict_probs(model, te, device)
        runs.append(dict(info, threshold=thr, **{f"val_{k}": v for k, v in val.items()}, _test_probs=test_probs))
        hists += [dict(h, seed=seed) for h in hist]
        key = (val["macro_f1"], -info["val_loss"])
        if best is None or key > best[0]:
            save_checkpoint(model, args.out, dict(threshold=thr, max_length=cfg["max_length"], seed=seed, lr=lr,
                                                  best_epoch=info["best_epoch"], selected_by="validation macro F1"))
            best = (key, seed)
        del model
        free(device)

    # Only now: score each seed once on test (stability), with its own validation threshold.
    for r in runs:
        r.update({f"test_{k}": v for k, v in scores(data["test"], r.pop("_test_probs"), r["threshold"]).items()})
        r["is_router"] = r["seed"] == best[1]
    stab = pd.DataFrame(runs)
    stab.to_csv(RESULTS_DIR / "final_seed_runs.csv", index=False)
    pd.DataFrame(hists).to_csv(RESULTS_DIR / "training_history.csv", index=False)

    sel_runs = RESULTS_DIR / "selection_runs.csv"
    sel_sec = pd.read_csv(sel_runs)["train_time_sec"].sum() if sel_runs.exists() else 0   # failed runs have no time
    gpu_min = (sel_sec + stab.train_time_sec.sum()) / 60
    log = dict(
        base_model=model_name, learning_rate=lr, router_seed=int(best[1]), seeds=FINAL_SEEDS, **cfg,
        loss="cross-entropy (type) + binary cross-entropy (escalation) + cross-entropy (language), summed",
        optimizer="AdamW, linear warmup then decay, gradient clipping 1.0, mixed precision on GPU",
        checkpoint_rule="epoch with lowest validation loss (early stop after 6 epochs without improvement)",
        router_rule="seed with the highest validation macro F1; escalation cut-off chosen on validation (F2)",
        splits={k: len(v) for k, v in data.items()},
        hardware=torch.cuda.get_device_name(0) if device.type == "cuda" else platform.processor() or "cpu",
        minutes_per_final_run=round(stab.train_time_sec.mean() / 60, 2),
        total_gpu_minutes_all_runs=round(gpu_min, 1),
        cost_usd_per_final_run=round(stab.train_time_sec.mean() / 3600 * GPU_USD_PER_HOUR, 3),
        cost_usd_all_runs=round(gpu_min / 60 * GPU_USD_PER_HOUR, 2),
        cost_assumption=f"{GPU_USD_PER_HOUR} USD per GPU hour (on-demand T4); cash cost on free Kaggle is 0",
        test_type_accuracy_over_seeds=dict(mean=round(stab.test_type_accuracy.mean(), 3),
                                           std=round(stab.test_type_accuracy.std(), 3),
                                           min=round(stab.test_type_accuracy.min(), 3),
                                           max=round(stab.test_type_accuracy.max(), 3)),
        versions=dict(torch=torch.__version__, transformers=__import__("transformers").__version__,
                      python=platform.python_version()),
    )
    (RESULTS_DIR / "training_log.json").write_text(json.dumps(log, indent=1, default=float), encoding="utf-8")
    cols = ["seed", "is_router", "best_epoch", "threshold", "val_macro_f1", "test_type_accuracy", "test_macro_f1",
            "test_escalation_recall"]
    print("\n" + stab[cols].round(3).to_string(index=False))
    print(f"\nRouter checkpoint (seed {best[1]}) saved to {args.out}")
    print("Next: python -m northstar.agent.router --split test --model finetuned")


# ---------------------------------------------------------------------------
# Step 3 (optional): learning curve over training-set size, validation only
# ---------------------------------------------------------------------------
def stratified_subset(train: pd.DataFrame, fraction: float, seed: int) -> pd.DataFrame:
    """Keep the same share of every request type (at least 1 chat each), drawn with the seed."""
    parts = [g.sample(n=max(1, round(fraction * len(g))), random_state=seed) for _, g in train.groupby("request_type")]
    return pd.concat(parts).reset_index(drop=True)


def run_datasize(args, data, device, cfg) -> None:
    sel_path = RESULTS_DIR / "selection_summary.json"
    sel = json.loads(sel_path.read_text()) if sel_path.exists() else {}
    model_name = args.model or sel.get("chosen_model") or "xlm-roberta-base"
    lr = args.lr or sel.get("chosen_lr") or 2e-5
    rows = []
    for frac in DATASIZE_FRACTIONS:
        for seed in DATASIZE_SEEDS:
            sub = {**data, "train": stratified_subset(data["train"], frac, seed)}
            print(f"\n[datasize] {len(sub['train'])} training chats ({frac:.0%})  seed={seed}")
            model, _, _, vp, info = train_one(model_name, lr, seed, sub, device, cfg, verbose=not args.quiet)
            rows.append(dict(info, fraction=frac, train_chats=len(sub["train"]),
                             **{f"val_{k}": v for k, v in scores(data["validation"], vp).items()}))
            del model
            free(device)
            pd.DataFrame(rows).to_csv(RESULTS_DIR / "datasize_runs.csv", index=False)   # saved after every run
    out = pd.DataFrame(rows).groupby("train_chats")[["val_type_accuracy", "val_macro_f1"]].agg(["mean", "std"])
    print("\n" + out.round(3).to_string())
    print("Next (no GPU): python -m northstar.finetune.datasize")


# ---------------------------------------------------------------------------
# Step 4 (optional): LoRA against full fine-tuning, validation only
# ---------------------------------------------------------------------------
def run_lora(args, data, device, cfg) -> None:
    sel_path = RESULTS_DIR / "selection_summary.json"
    sel = json.loads(sel_path.read_text()) if sel_path.exists() else {}
    model_name = args.model or sel.get("chosen_model") or "xlm-roberta-base"
    rows = []
    for lr in LORA_LRS:
        for seed in LORA_SEEDS:
            print(f"\n[lora] {model_name}  lr={lr}  seed={seed}")
            model, _, _, vp, info = train_one(model_name, lr, seed, data, device, cfg, verbose=not args.quiet, lora=LORA)
            rows.append(dict(info, method="lora", **{f"val_{k}": v for k, v in scores(data["validation"], vp).items()}))
            del model
            free(device)
            pd.DataFrame(rows).to_csv(RESULTS_DIR / "lora_runs.csv", index=False)
    lora = pd.DataFrame(rows)
    best_lr = lora.groupby("lr").val_macro_f1.mean().idxmax()
    best = lora[lora.lr == best_lr]
    summary = {"lora_settings": LORA, "lora_best_lr": float(best_lr),
               "rule": "LoRA learning rate chosen by mean validation macro F1 over 3 seeds",
               "lora": {"val_macro_f1_mean": round(best.val_macro_f1.mean(), 3), "val_macro_f1_std": round(best.val_macro_f1.std(), 3),
                        "val_type_accuracy_mean": round(best.val_type_accuracy.mean(), 3),
                        "trainable_params": int(best.trainable_params.iloc[0]),
                        "minutes_per_run": round(best.train_time_sec.mean() / 60, 2)},
               "split_used": "validation (30 chats); test not touched"}
    full_path = RESULTS_DIR / "final_seed_runs.csv"
    if full_path.exists():                       # full fine-tuning, same model and data, 5 seeds (step 2)
        full = pd.read_csv(full_path)
        summary["full_finetuning"] = {"val_macro_f1_mean": round(full.val_macro_f1.mean(), 3),
                                      "val_macro_f1_std": round(full.val_macro_f1.std(), 3),
                                      "val_type_accuracy_mean": round(full.val_type_accuracy.mean(), 3),
                                      "minutes_per_run": round(full.train_time_sec.mean() / 60, 2)}
    (RESULTS_DIR / "lora_summary.json").write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=float))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["select", "final", "datasize", "lora"])
    ap.add_argument("--models", nargs="+", default=CANDIDATE_MODELS)
    ap.add_argument("--lrs", nargs="+", type=float, default=CANDIDATE_LRS)
    ap.add_argument("--model", default=None, help="final: override the base model chosen in step 1")
    ap.add_argument("--lr", type=float, default=None, help="final: override the learning rate chosen in step 1")
    ap.add_argument("--out", type=Path, default=Path("models/finetuned_router"))
    ap.add_argument("--epochs", type=int, default=DEFAULTS["epochs"])
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    cfg = dict(DEFAULTS, epochs=a.epochs)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", device, torch.cuda.get_device_name(0) if device.type == "cuda" else "")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    data = split_frames()
    print({k: len(v) for k, v in data.items()})
    {"select": run_select, "final": run_final, "datasize": run_datasize, "lora": run_lora}[a.step](a, data, device, cfg)


if __name__ == "__main__":
    main()
