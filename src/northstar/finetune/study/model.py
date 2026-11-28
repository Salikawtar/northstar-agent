"""The router model: one shared text encoder with several small answer-heads on top.

How it works, in plain words
1. A pretrained language model (the "encoder", here XLM-RoBERTa) reads the chat text and turns every
   token into a list of numbers.
2. We keep only the numbers at the first position (the special start token). By the way these models
   are built, that position summarises the whole message, like a one-line digest of the chat.
3. Each "head" is one small linear layer that turns that digest into the answers for one question.
   The type head gives 10 scores (one per request type); the escalation head gives 1 score
   (positive means "a person should take over"); a language head gives 2; a reason head gives 7; an attack
   head gives 1 (positive means "this chat tries to trick the assistant").
4. Training adjusts the encoder and the heads together, so the digest becomes useful for every question.

The original notebook had exactly this shape with two heads (type and escalation); this file makes the
set of heads configurable so later steps can add language and reason without touching the rest.
"""
from __future__ import annotations

import torch
import torch.nn as nn

# How many output numbers each question needs.
HEAD_SIZES = {"type": 10, "escalation": 1, "language": 2, "reason": 7, "attack": 1}
BINARY_HEADS = ("escalation", "attack")   # yes/no questions: one score each, positive means "yes"


class RouterModel(nn.Module):
    def __init__(self, model_name: str, heads: dict, dropout: float = 0.2, encoder=None, lora: dict | None = None):
        """heads: which questions to answer, e.g. {"type": 10, "escalation": 1}.
        encoder: pass a ready-made encoder (used only by tests); normally it is downloaded.
        lora: None for ordinary fine-tuning (every weight is adjusted). Or the LoRA settings, e.g.
              {"r": 8, "lora_alpha": 16, "target_modules": ["query", "value"]}: the pretrained weights are
              frozen and only small add-on matrices inside the attention layers (plus the heads) are trained,
              about 0.1% as many numbers, which is cheaper and may be steadier on a small dataset."""
        super().__init__()
        if encoder is None:
            from transformers import AutoModel
            encoder = AutoModel.from_pretrained(model_name)      # pretrained weights, downloaded the first time
        hidden = encoder.config.hidden_size                      # size of the digest vector (768 for XLM-R base)
        if lora:
            from peft import LoraConfig, get_peft_model
            encoder = get_peft_model(encoder, LoraConfig(**lora))    # freezes the encoder, adds the small trainable add-ons
        self.encoder = encoder
        self.dropout = nn.Dropout(dropout)                       # randomly blanks 20% of the digest while training,
                                                                 # so no head can lean on one single number
        # One linear layer per question: digest (hidden numbers) -> that question's scores.
        # (Keys get a "head_" prefix because PyTorch refuses a layer named "type": that word is already taken.)
        self.heads = nn.ModuleDict({f"head_{name}": nn.Linear(hidden, n_out) for name, n_out in heads.items()})

    def forward(self, input_ids, attention_mask):
        """input_ids: token numbers [batch, length]; attention_mask: 1 for real tokens, 0 for padding."""
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        digest = self.dropout(out.last_hidden_state[:, 0, :])    # first position = summary of the whole chat
        scores = {key.removeprefix("head_"): head(digest) for key, head in self.heads.items()}   # back to plain names
        for name in BINARY_HEADS:
            if name in scores:
                scores[name] = scores[name].squeeze(-1)   # one number per chat, not a 1-long list
        return scores
