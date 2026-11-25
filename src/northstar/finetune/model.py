"""The fine-tuned router model: one shared encoder, three small heads.

The encoder reads the same conversation text the prompted router reads
(customer, agent, customer). Three linear heads sit on the first token's
vector and answer the three questions the router must answer:

- request type: which of the 10 labels (10-way choice)
- escalation: must a person take over (yes/no)
- language: English or French (2-way choice)

A checkpoint is a folder with two files: `weights.pt` (the trained numbers)
and `router_config.json` (base model name, labels, escalation threshold,
input length). Keeping the settings next to the weights means a checkpoint
always loads with the exact settings it was trained with.
"""
from __future__ import annotations

import json
from pathlib import Path

import torch
import torch.nn as nn
from transformers import AutoConfig, AutoModel

from northstar.contracts import Language, RequestType

REQUEST_TYPES = [t.value for t in RequestType]   # same order as the contract, never typed by hand
LANGUAGES = [lang.value for lang in Language]


class RouterClassifier(nn.Module):
    def __init__(self, model_name: str, dropout: float = 0.2, pretrained: bool = True):
        super().__init__()
        self.model_name = model_name
        # pretrained=False builds the same shape with random numbers; used when
        # loading a saved checkpoint (the saved weights replace them) and in tests.
        self.encoder = (AutoModel.from_pretrained(model_name) if pretrained
                        else AutoModel.from_config(AutoConfig.from_pretrained(model_name)))
        hidden = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.type_head = nn.Linear(hidden, len(REQUEST_TYPES))
        self.escalation_head = nn.Linear(hidden, 1)
        self.language_head = nn.Linear(hidden, len(LANGUAGES))

    def forward(self, input_ids, attention_mask):
        h = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state[:, 0, :]
        h = self.dropout(h)
        return self.type_head(h), self.escalation_head(h).squeeze(-1), self.language_head(h)


def save_checkpoint(model: RouterClassifier, folder: Path, config: dict) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), folder / "weights.pt")
    cfg = {"base_model": model.model_name, "request_types": REQUEST_TYPES, "languages": LANGUAGES, **config}
    (folder / "router_config.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")


def load_checkpoint(folder: Path, device: str | torch.device = "cpu") -> tuple[RouterClassifier, dict]:
    folder = Path(folder)
    cfg = json.loads((folder / "router_config.json").read_text(encoding="utf-8"))
    if cfg["request_types"] != REQUEST_TYPES:
        raise ValueError("Checkpoint labels do not match the RouterOutput contract; retrain the model.")
    model = RouterClassifier(cfg["base_model"], pretrained=False)
    model.load_state_dict(torch.load(folder / "weights.pt", map_location=device))
    return model.to(device).eval(), cfg
