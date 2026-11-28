"""Cross-validated training of the router model (used by notebook 02 and later steps).

One "run" = train one fresh model on 4 folds of the 160-chat pool, and score the 5th (held-out) fold
after EVERY epoch. Everything a later analysis needs is saved: the raw scores ("logits") of every
held-out chat at every epoch. Thresholds, calibration, seed ensembles and the cascade can then be
studied on a laptop without retraining anything.

The training recipe defaults reproduce the original notebook: same model, same loss (type cross-entropy
plus escalation binary cross-entropy, summed), AdamW at 2e-5, batch 16, 30 epochs, constant learning
rate, no warmup, no gradient clipping. Two things differ on purpose, and neither should change results
beyond noise: chats are padded only to the longest in each batch (faster), and the maths can run in half
precision on the GPU (faster).

The 40 test chats are never loaded here: `protocol.pool()` does not contain them.
"""
from __future__ import annotations

import gc
import json
import math
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from northstar.finetune.study import protocol as P
from northstar.finetune.study.model import BINARY_HEADS, HEAD_SIZES, RouterModel

# Which column of the dataset holds the correct answer for each question.
HEAD_LABEL_COLUMN = {"type": "type_label", "escalation": "escalation_label",
                     "language": "language_label", "reason": "reason_label", "attack": "attack_label"}


@dataclass
class TrainConfig:
    model_name: str = "xlm-roberta-base"
    lr: float = 2e-5                  # how big each learning step is
    weight_decay: float = 0.01        # gentle pull of weights towards zero; AdamW's default, as in the notebook
    epochs: int = 30                  # one epoch = one pass over the training chats
    batch_size: int = 16              # chats processed together in one learning step
    max_length: int = 320             # chats longer than this many tokens are cut (the longest full conversation
                                      # is about 280, so none are). The notebook used 256 on shorter text.
    dropout: float = 0.2
    schedule: str = "constant"        # "constant" = the notebook; "linear" = warm up, then decay to zero
    warmup_ratio: float = 0.0         # share of steps spent warming up (only used by "linear")
    grad_clip: float = 0.0            # 0 = no clipping (the notebook); otherwise cap the size of each update
    fp16: bool = True                 # half-precision maths on a GPU: faster, same results within noise
    heads: tuple = ("type", "escalation")
    lora: bool = False                # True = LoRA: freeze the pretrained weights, train small add-on matrices
    lora_r: int = 8                   # size of the add-on matrices (rank); bigger = more flexible
    lora_alpha: int = 16              # strength of the add-on's effect
    lora_dropout: float = 0.1


def set_seed(seed: int) -> None:
    """Make a run repeatable: same seed -> same starting weights and the same chat order."""
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def _batches(order, token_ids, pad_id, device, batch_size):
    """Yield (chat positions, token tensor, mask tensor), padding only to the longest chat in the batch."""
    for start in range(0, len(order), batch_size):
        chunk = np.asarray(order[start:start + batch_size])
        longest = max(len(token_ids[i]) for i in chunk)
        ids = torch.full((len(chunk), longest), pad_id, dtype=torch.long)     # filled with the padding token
        mask = torch.zeros((len(chunk), longest), dtype=torch.long)           # 1 = real token, 0 = padding
        for row, i in enumerate(chunk):
            n = len(token_ids[i])
            ids[row, :n] = torch.tensor(token_ids[i])
            mask[row, :n] = 1
        yield chunk, ids.to(device), mask.to(device)


def _total_loss(scores: dict, labels: dict, chunk: np.ndarray) -> torch.Tensor:
    """Sum of one loss per question, as in the notebook: cross-entropy for the pick-one questions,
    binary cross-entropy for the yes/no questions (escalation, attack)."""
    idx = torch.as_tensor(chunk, device=next(iter(labels.values())).device)
    loss = 0.0
    for name, s in scores.items():
        y = labels[name][idx]
        if name in BINARY_HEADS:
            loss = loss + F.binary_cross_entropy_with_logits(s.float(), y)
        else:
            loss = loss + F.cross_entropy(s.float(), y)
    return loss


def _make_scheduler(opt, cfg: TrainConfig, total_steps: int):
    """Learning-rate plan. "constant" keeps it fixed (the notebook). "linear" ramps up over the warmup
    steps, then falls in a straight line to zero."""
    if cfg.schedule == "constant":
        return None
    warm = int(cfg.warmup_ratio * total_steps)

    def factor(step: int) -> float:
        if step < warm:
            return (step + 1) / max(1, warm)
        return max(0.0, (total_steps - step) / max(1, total_steps - warm))
    return torch.optim.lr_scheduler.LambdaLR(opt, factor)


@torch.no_grad()
def _predict(model, order, token_ids, labels, cfg, pad_id, device, use_amp):
    """Scores and average loss for the chats in `order` (no learning, dropout off)."""
    model.eval()
    parts = {name: [] for name in cfg.heads}
    loss_sum = 0.0
    for chunk, ids, mask in _batches(order, token_ids, pad_id, device, cfg.batch_size):
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
            scores = model(ids, mask)
        loss_sum += float(_total_loss(scores, labels, chunk)) * len(chunk)
        for name, s in scores.items():
            parts[name].append(s.float().cpu().numpy())
    return {name: np.concatenate(v, axis=0) for name, v in parts.items()}, loss_sum / len(order)


def run_one(cfg: TrainConfig, token_ids, labels, train_idx, val_idx, seed, pad_id, device, epochs=None,
            encoder_factory=None, score_every_epoch: bool = True, return_model: bool = False) -> dict:
    """Train one model from scratch on `train_idx`; after each epoch score `val_idx`.
    The final run (final_run.py) scores only after the last epoch (`score_every_epoch=False`), so no test chat is
    scored at any other epoch, and may keep the trained model (`return_model=True`, under the key "model")."""
    epochs = epochs or cfg.epochs
    use_amp = bool(cfg.fp16 and device.type == "cuda")
    set_seed(seed)
    encoder = encoder_factory() if encoder_factory else None
    lora = (dict(r=cfg.lora_r, lora_alpha=cfg.lora_alpha, lora_dropout=cfg.lora_dropout, bias="none",
                 target_modules=["query", "value"]) if cfg.lora else None)     # add-ons on the attention "query" and "value" layers
    model = RouterModel(cfg.model_name, {h: HEAD_SIZES[h] for h in cfg.heads}, cfg.dropout, encoder, lora).to(device)
    trainable = [p for p in model.parameters() if p.requires_grad]            # frozen weights are left out of the optimiser
    n_trainable, n_total = sum(p.numel() for p in trainable), sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(trainable, lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps_per_epoch = math.ceil(len(train_idx) / cfg.batch_size)
    scheduler = _make_scheduler(opt, cfg, epochs * steps_per_epoch)
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)     # keeps tiny half-precision gradients from vanishing
    shuffle_rng = np.random.default_rng(seed)                   # decides the chat order in each epoch

    hist = {"train_loss": [], "val_loss": [], **{f"logits_{h}": [] for h in cfg.heads}}
    for epoch in range(epochs):
        model.train()                                           # dropout on
        loss_sum = 0.0
        for chunk, ids, mask in _batches(shuffle_rng.permutation(train_idx), token_ids, pad_id, device, cfg.batch_size):
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
                scores = model(ids, mask)                       # forward pass: the model's current guesses
            loss = _total_loss(scores, labels, chunk)           # how wrong the guesses are
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()                       # work out which way to nudge every weight
            if cfg.grad_clip > 0:
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
            scaler.step(opt)                                    # take the learning step
            scaler.update()
            if scheduler:
                scheduler.step()
            loss_sum += float(loss) * len(chunk)
        hist["train_loss"].append(loss_sum / len(train_idx))
        if score_every_epoch or epoch == epochs - 1:
            logits, val_loss = _predict(model, val_idx, token_ids, labels, cfg, pad_id, device, use_amp)
            hist["val_loss"].append(val_loss)
            for h in cfg.heads:
                hist[f"logits_{h}"].append(logits[h])
    kept = model if return_model else None
    del model, opt, scaler
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()
    out = {k: np.array(v, dtype=np.float32) for k, v in hist.items()}
    out["n_trainable"], out["n_total"] = np.array(n_trainable), np.array(n_total)    # how many numbers were trained
    if kept is not None:
        out["model"] = kept
    return out


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=P.ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def run_cv(cfg: TrainConfig, variant: str, out_dir, rep: int = 0, seeds=P.CV_SEEDS, folds=None, epochs=None,
           tokenizer=None, encoder_factory=None, device=None, verbose: bool = True) -> list:
    """Cross-validate one configuration on one input variant. Files that already exist are skipped, so a
    crashed or interrupted session can simply be run again and carries on where it stopped."""
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pool = P.pool(P.load_all())
    fold_of = dict(zip(*[P.fold_assignments(rep)[c] for c in ("id", "fold")]))
    fold_arr = pool["id"].map(fold_of).values
    if tokenizer is None:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(cfg.model_name)
    pad_id = tokenizer.pad_token_id

    token_ids = tokenizer(list(P.input_text(pool, variant)), truncation=True, max_length=cfg.max_length)["input_ids"]
    labels = {h: torch.tensor(pool[HEAD_LABEL_COLUMN[h]].values,
                              dtype=torch.float32 if h in BINARY_HEADS else torch.long).to(device)
              for h in cfg.heads}

    out = Path(out_dir) / variant
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(dict(
        config=asdict(cfg), variant=variant, rep=rep, seeds=list(seeds), epochs_run=epochs or cfg.epochs,
        git_commit=_git_commit(), torch=torch.__version__, device=str(device),
        gpu=torch.cuda.get_device_name(0) if device.type == "cuda" else "none",
        dataset_sha256=P.EXPECTED_SHA256, folds_sha256=P.sha256_of(P.FOLDS_PATH),
        mean_tokens=float(np.mean([len(t) for t in token_ids]))), indent=2), encoding="utf-8")

    saved = []
    for seed in seeds:
        for k in (range(P.N_FOLDS) if folds is None else folds):
            path = out / f"rep{rep}_seed{seed}_fold{k}.npz"
            if path.exists():
                saved.append(path)
                continue
            val_idx = np.where(fold_arr == k)[0]
            train_idx = np.where(fold_arr != k)[0]
            t0 = time.time()
            hist = run_one(cfg, token_ids, labels, train_idx, val_idx, seed, pad_id, device, epochs, encoder_factory)
            hist["seconds"] = np.array(time.time() - t0)                       # how long this run took
            np.savez_compressed(path, ids=pool["id"].values[val_idx].astype(str), fold=k, seed=seed, **hist)
            saved.append(path)
            if verbose:
                print(f"[{variant}] seed {seed} fold {k}: {time.time() - t0:5.0f}s | held-out loss at last epoch "
                      f"{hist['val_loss'][-1]:.3f}", flush=True)
    return saved
