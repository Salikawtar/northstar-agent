"""The figure of report page 4: why the fine-tuned router lost, and when it would pay.

Two small charts side by side, wide and short so they fit one report page:
- left: request-type accuracy against the number of training chats (validation), with the
  prompted Haiku router as the line to reach and the fine-tuned test score for honesty;
- right: what each router costs a month as volume grows, with the two break-even volumes.

Only committed result files are read, so it needs no GPU and no key:
    results/datasize_runs.csv, results/datasize_summary.json   (datasize.py)
    results/comparison_table.csv                               (compare.py)
    results/breakeven.json                                     (breakeven.py)
    config/economics.yaml                                      Northstar's monthly volume

    python -m northstar.finetune.report_figure

Writes results/page4_figure.png. Nothing is typed by hand: every mark and label is a number
from those files (docs/report/page4_finetune.md quotes the same numbers, and a test checks them).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from northstar.config import ROOT

HERE = Path(__file__).parent / "results"
FT, SMALL, LARGE = "Fine-tuned (XLM-R)", "Small prompted (Haiku)", "Large prompted (Sonnet)"

# One colour per router, the same in both charts. The three were checked together for
# colour-blind readers (protan and deutan), so no pair of lines can be confused.
COLOUR = {FT: "#00b894", SMALL: "#257de0", LARGE: "#f47230"}
LEGEND = {FT: "Fine-tuned XLM-RoBERTa", SMALL: "Haiku 5.5, prompted (small)", LARGE: "Sonnet 5.5, prompted (large)"}
INK, QUIET, GRID, AXIS = "#191919", "#666666", "#e7e7e7", "#c2c2c2"


def numbers() -> dict:
    """Everything the figure draws, read from the result files."""
    table = pd.read_csv(HERE / "comparison_table.csv").set_index("router")
    size = json.loads((HERE / "datasize_summary.json").read_text(encoding="utf-8"))
    be = json.loads((HERE / "breakeven.json").read_text(encoding="utf-8"))
    econ = yaml.safe_load((ROOT / "config" / "economics.yaml").read_text(encoding="utf-8"))
    return {
        "runs": pd.read_csv(HERE / "datasize_runs.csv")[["train_chats", "val_type_accuracy"]],
        "curve": [(int(p["train_chats"]), float(p["acc_mean"])) for p in size["curve_validation"]],
        "haiku_validation": float(size["validation"]["haiku"]),
        "test_accuracy": {k: float(table.loc[k, "type_accuracy"]) for k in (FT, SMALL, LARGE)},
        "usd_per_chat": {k: float(table.loc[k, "cost_usd_per_chat"]) for k in (SMALL, LARGE)},
        "server_usd_per_month": float(be["base_case"]["monthly_fixed_usd"]),
        "breakeven": {SMALL: int(be["base_case"]["vs_haiku_chats_per_month"]),
                      LARGE: int(be["base_case"]["vs_sonnet_chats_per_month"])},
        "northstar_volume": int(econ["northstar_volume"]),
    }


def draw(n: dict, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter, NullLocator

    plt.rcParams.update({"font.size": 7.5, "axes.edgecolor": AXIS, "axes.linewidth": 0.6,
                         "xtick.color": QUIET, "ytick.color": QUIET, "axes.labelcolor": QUIET, "text.color": INK})
    fig, (left, right) = plt.subplots(1, 2, figsize=(6.5, 2.05), dpi=200, gridspec_kw={"width_ratios": [1, 1.12]})
    ring = {"markeredgecolor": "white", "markeredgewidth": 1.0}

    # Left: accuracy against training chats. The curve is validation; the diamond is the test score.
    xs, ys = zip(*n["curve"])
    left.axhline(n["haiku_validation"], color=COLOUR[SMALL], lw=1.6)
    left.scatter(n["runs"].train_chats, n["runs"].val_type_accuracy, s=9, color=COLOUR[FT], alpha=0.35, linewidths=0)
    left.plot(xs, ys, "o-", color=COLOUR[FT], lw=1.8, ms=5.5, **ring)
    left.plot([xs[-1]], [n["test_accuracy"][FT]], "D", color="white", ms=5, markeredgecolor=COLOUR[FT], markeredgewidth=1.4)
    left.annotate(f"{ys[0]:.0%}", (xs[0], ys[0]), xytext=(6, -2), textcoords="offset points", va="center")
    left.annotate(f"validation {ys[-1]:.0%}", (xs[-1], ys[-1]), xytext=(7, -6.5), textcoords="offset points", va="center")
    left.annotate(f"test {100 * n['test_accuracy'][FT]:.1f}%", (xs[-1], n["test_accuracy"][FT]),
                  xytext=(7, -4.5), textcoords="offset points", va="center")
    left.annotate(f"Haiku, no training: {n['haiku_validation']:.0%} ({100 * n['test_accuracy'][SMALL]:.1f}% on test)",
                  (xs[0], n["haiku_validation"]), xytext=(-2, 4), textcoords="offset points")
    left.set_xscale("log")
    left.set_xlim(xs[0] * 0.88, xs[-1] * 1.72)          # room on the right for the two labels
    left.set_ylim(0, 1)
    left.xaxis.set_minor_locator(NullLocator())
    left.set_xticks(list(xs), [str(x) for x in xs])
    left.set_yticks([0, 0.25, 0.5, 0.75, 1.0], ["0%", "25%", "50%", "75%", "100%"])
    left.set_xlabel("Training chats (log scale)")
    left.set_title("Request types right, by training data", fontsize=8, loc="left", pad=4)

    # Right: monthly cost of the router alone. The fine-tuned router is a server, flat at any volume.
    vols = np.geomspace(1_000, 1_000_000, 60)
    server = n["server_usd_per_month"]
    right.plot(vols, [server] * len(vols), color=COLOUR[FT], lw=1.8)
    for key in (SMALL, LARGE):
        right.plot(vols, vols * n["usd_per_chat"][key], color=COLOUR[key], lw=1.8)
        at = n["breakeven"][key]
        right.plot([at], [server], "o", color=INK, ms=4.5, **ring)
        right.annotate(f"{at:,}", (at, server), xytext=(0, 5), textcoords="offset points", ha="center")
    home = n["northstar_volume"]
    right.axvline(home, color=AXIS, lw=0.8, zorder=0)
    right.annotate(f"Northstar: {home:,} chats", (home, 0.42), xytext=(3, 0), textcoords="offset points",
                   color=QUIET, va="bottom")
    right.annotate(f"${server:,.0f} server", (1_150, server), xytext=(0, 4), textcoords="offset points")
    right.set_xscale("log")
    right.set_yscale("log")
    right.set_xlim(1_000, 1_000_000)
    right.set_ylim(0.3, 9_000)
    right.xaxis.set_minor_locator(NullLocator())
    right.yaxis.set_minor_locator(NullLocator())
    right.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:,.0f}"))
    right.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"${y:,.0f}"))
    right.set_yticks([1, 10, 100, 1_000])
    right.set_xlabel("Chats a month (log scale); dots: break-even")
    right.set_title("Router cost a month, by volume", fontsize=8, loc="left", pad=4)

    for ax in (left, right):
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(length=2.5, width=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    keys = [Line2D([], [], color=COLOUR[k], lw=1.8, label=LEGEND[k]) for k in (FT, SMALL, LARGE)]
    fig.legend(handles=keys, loc="upper center", ncol=3, frameon=False, fontsize=7.5, handlelength=2.0,
               columnspacing=2.2, bbox_to_anchor=(0.5, 1.0), borderaxespad=0.1)
    fig.tight_layout(pad=0.4, w_pad=1.6, rect=(0, 0, 1, 0.92))
    fig.savefig(out)
    plt.close(fig)


def build() -> Path | None:
    out = HERE / "page4_figure.png"
    try:
        draw(numbers(), out)
    except ImportError:
        # The figure only draws numbers the tables already hold; without matplotlib the stage still passes.
        print("matplotlib not installed: skipped the page 4 figure (pip install -r requirements.txt adds it)")
        return None
    return out


if __name__ == "__main__":
    print(build())
