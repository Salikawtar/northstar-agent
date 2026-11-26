"""When does the fine-tuned router pay off? (Phase 5)

The prompted routers cost money per chat. The fine-tuned router costs nothing per chat,
but needs a server running all month (fixed cost) and an occasional retrain.
Break-even volume = monthly fixed cost / prompted cost per chat.

    python -m northstar.finetune.breakeven

Inputs, all from files in the repository (nothing typed by hand here):
    results/comparison_table.csv   measured cost per chat and latency on the 40 test chats
    results/training_log.json      measured GPU cost of one full training (selection + final)
    config/settings.yaml           finetuned_router_hosting: server price and planning rules

Writes results/breakeven.csv (1,000 / 100,000 / 1,000,000 chats a month, the economics
volumes) and results/breakeven.json (break-even volumes, capacity, sensitivity).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from northstar.config import settings

HERE = Path(__file__).parent / "results"
VOLUMES = [1_000, 100_000, 1_000_000]          # chats per month: the three volumes the project brief names
FT, SMALL, LARGE = "Fine-tuned (XLM-R)", "Small prompted (Haiku)", "Large prompted (Sonnet)"


def monthly_fixed(h: dict, train_cost: float, usd_per_hour: float, servers: int) -> float:
    return servers * usd_per_hour * h["hours_per_month"] + h["retrains_per_year"] * train_cost / 12


def build() -> tuple[pd.DataFrame, dict]:
    h = settings()["finetuned_router_hosting"]
    table = pd.read_csv(HERE / "comparison_table.csv").set_index("router")
    log = json.loads((HERE / "training_log.json").read_text())
    train_cost = float(log["cost_usd_all_runs"])     # one full retrain = selection + 5 seeds

    # Capacity: one chat at a time per server (conservative: no batching), at the planned load.
    sec_per_chat = table.loc[FT, "latency_ms_median"] / 1000
    capacity = 3600 / sec_per_chat * h["hours_per_month"] * h["max_utilisation"]

    rows = []
    for v in VOLUMES:
        servers = max(h["servers"], math.ceil(v / capacity))
        ft = monthly_fixed(h, train_cost, h["usd_per_hour"], servers)
        rows.append({"chats_per_month": v,
                     "finetuned_usd": round(ft, 2),
                     "finetuned_servers": servers,
                     "haiku_usd": round(v * table.loc[SMALL, "cost_usd_per_chat"], 2),
                     "sonnet_usd": round(v * table.loc[LARGE, "cost_usd_per_chat"], 2)})
    scen = pd.DataFrame(rows)
    scen["cheapest"] = scen[["finetuned_usd", "haiku_usd", "sonnet_usd"]].idxmin(axis=1).str.replace("_usd", "")

    def breakeven(usd_per_hour: float, servers: int) -> dict:
        fixed = monthly_fixed(h, train_cost, usd_per_hour, servers)
        return {"monthly_fixed_usd": round(fixed, 2),
                "vs_haiku_chats_per_month": int(round(fixed / table.loc[SMALL, "cost_usd_per_chat"], -3)),
                "vs_sonnet_chats_per_month": int(round(fixed / table.loc[LARGE, "cost_usd_per_chat"], -2))}

    summary = {
        "base_case": breakeven(h["usd_per_hour"], h["servers"]),
        "sensitivity": {
            "committed_1_year_price": breakeven(h["usd_per_hour_committed"], h["servers"]),
            "two_servers_for_redundancy": breakeven(h["usd_per_hour"], 2),
        },
        "capacity_chats_per_month_per_server": int(round(capacity, -4)),
        "inputs": {"server": h["server"], "usd_per_hour": h["usd_per_hour"],
                   "retrain_cost_usd": train_cost, "retrains_per_year": h["retrains_per_year"],
                   "haiku_usd_per_chat": table.loc[SMALL, "cost_usd_per_chat"],
                   "sonnet_usd_per_chat": table.loc[LARGE, "cost_usd_per_chat"],
                   "finetuned_ms_per_chat": table.loc[FT, "latency_ms_median"]},
        "not_included": "labelling new chats for retraining (people's time), engineering time to run the "
                        "server, and the cost of mistakes (Phase 6 economics adds these)",
    }
    scen.to_csv(HERE / "breakeven.csv", index=False)
    (HERE / "breakeven.json").write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    return scen, summary


def main() -> None:
    scen, summary = build()
    print(scen.to_string(index=False))
    print(json.dumps(summary, indent=1, default=float))


if __name__ == "__main__":
    main()
