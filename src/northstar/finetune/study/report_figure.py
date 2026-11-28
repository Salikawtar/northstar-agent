"""The figure of report page 4, for the fine-tuning study.

Two small charts side by side, the same size and colours as the first version's figure:
- left: each router's routing step on the 40 test chats and on the 31 fresh chats (another model family),
  the study's main finding: the fine-tuned router is close to Haiku on test and falls on fresh chats;
- right: what each router costs a month as volume grows, with the break-even volumes: the first version's
  chart (same base model, same CPU server) with Jev added. Every prompted router is priced as it runs in the
  agent, on the whole conversation: Haiku and Sonnet from the first comparison, Jev from the study.

Only committed result files are read (no GPU, no key):
    results/step06/final_scores.csv                     the study's final run (first message)
    ../results/breakeven.json, comparison_table.csv     the break-even of the first version
    python -m northstar.finetune.study.report_figure
Writes results/page4_figure.png. Every mark and label is a number from those files; a test checks the page.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from northstar.finetune import report_figure as first
from northstar.finetune.study import protocol as P

OUT = P.STUDY / "results" / "page4_figure.png"
FT, SMALL, LARGE, JEV = first.FT, first.SMALL, first.LARGE, "Jev 1.14"
ROUTERS = {FT: "Fine-tuned, balanced", SMALL: "Haiku (team's router)", LARGE: "Sonnet", JEV: "Jev, same information"}
LABEL = {FT: "Fine-tuned (final)", SMALL: "Haiku 5.5", LARGE: "Sonnet 5.5", JEV: "Jev 1.14"}
# The first figure's three colours (checked together for colour-blind readers) and a neutral grey for Jev,
# which differs from them in lightness; every row is also named, so colour is never the only cue.
COLOUR = {**first.COLOUR, JEV: "#6f6f6f"}
ORDER = (SMALL, LARGE, JEV, FT)          # top to bottom


def numbers() -> dict:
    s_all = pd.read_csv(P.STUDY / "results" / "step06" / "final_scores.csv")
    s = s_all[s_all.input == "first_message"]

    def rate(dataset, key):
        d = s[(s.dataset == dataset) & s.router.str.startswith(ROUTERS[key])]
        assert len(d) == 1, (dataset, key)
        return float(d.handled_right.iloc[0]), int(d.chats.iloc[0])

    n = first.numbers()
    jev = s_all[(s_all.dataset == "test") & (s_all.input == "full_conversation") & s_all.router.str.startswith(ROUTERS[JEV])]
    assert len(jev) == 1
    n["usd_per_chat"][JEV] = float(jev.usd_per_1000.iloc[0]) / 1000
    n["breakeven"][JEV] = int(round(n["server_usd_per_month"] / n["usd_per_chat"][JEV], -3))   # rounded as breakeven.py does
    n["routing"] = {k: {"test": rate("test", k)[0], "fresh": rate("fresh", k)[0]} for k in ORDER}
    n["chats"] = {"test": rate("test", FT)[1], "fresh": rate("fresh", FT)[1]}
    return n


def draw(n: dict, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter, NullLocator

    plt.rcParams.update({"font.size": 7.5, "axes.edgecolor": first.AXIS, "axes.linewidth": 0.6,
                         "xtick.color": first.QUIET, "ytick.color": first.QUIET, "axes.labelcolor": first.QUIET,
                         "text.color": first.INK})
    fig, (left, right) = plt.subplots(1, 2, figsize=(6.5, 2.05), dpi=200, gridspec_kw={"width_ratios": [1, 1.12]})
    ring = {"markeredgecolor": "white", "markeredgewidth": 1.0}

    # Left: routing step right, test (filled) and fresh (open), one row per router.
    for y, key in enumerate(reversed(ORDER)):
        t, f = n["routing"][key]["test"], n["routing"][key]["fresh"]
        left.plot([f, t], [y, y], color=COLOUR[key], lw=1.6, alpha=0.55, solid_capstyle="round")
        left.plot([t], [y], "o", color=COLOUR[key], ms=5.5, **ring)
        left.plot([f], [y], "o", color="white", ms=5, markeredgecolor=COLOUR[key], markeredgewidth=1.4)
        left.annotate(f"{100 * t:.1f}%", (t, y), xytext=(6, 0), textcoords="offset points", va="center")
        left.annotate(f"{100 * f:.1f}%", (f, y), xytext=(-6, 0), textcoords="offset points", va="center", ha="right")
    left.set_yticks(range(len(ORDER)), [LABEL[k] for k in reversed(ORDER)])
    left.set_xlim(0.3, 1.08)
    left.set_ylim(-0.6, len(ORDER) - 0.4)
    left.set_xticks([0.4, 0.6, 0.8, 1.0], ["40%", "60%", "80%", "100%"])
    left.set_xlabel(f"● {n['chats']['test']} test chats   ○ {n['chats']['fresh']} fresh chats (another model family)")
    left.set_title("Routing step right: test vs fresh chats", fontsize=8, loc="left", pad=4)
    left.grid(axis="x", color=first.GRID, lw=0.6)

    # Right: monthly cost of the router alone (the first version's chart, same numbers).
    vols = np.geomspace(1_000, 1_000_000, 60)
    server = n["server_usd_per_month"]
    right.plot(vols, [server] * len(vols), color=COLOUR[FT], lw=1.8)
    for key in (SMALL, LARGE, JEV):
        right.plot(vols, vols * n["usd_per_chat"][key], color=COLOUR[key], lw=1.8)
        at = n["breakeven"][key]
        right.plot([at], [server], "o", color=first.INK, ms=4.5, **ring)
        below = key == JEV                   # Haiku's and Jev's dots are close: one label above, one below
        right.annotate(f"{at:,}", (at, server), xytext=(0, -10 if below else 5), textcoords="offset points", ha="center")
    home = n["northstar_volume"]
    right.axvline(home, color=first.AXIS, lw=0.8, zorder=0)
    right.annotate(f"Northstar: {home:,} chats", (home, 0.42), xytext=(3, 0), textcoords="offset points",
                   color=first.QUIET, va="bottom")
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
    right.grid(axis="y", color=first.GRID, lw=0.6)

    for ax in (left, right):
        ax.set_axisbelow(True)
        ax.tick_params(length=2.5, width=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    left.tick_params(axis="y", length=0)
    keys = [Line2D([], [], color=COLOUR[k], lw=1.8, label=LABEL[k]) for k in (FT, SMALL, LARGE, JEV)]
    fig.legend(handles=keys, loc="upper center", ncol=4, frameon=False, fontsize=7.5, handlelength=2.0,
               columnspacing=2.0, bbox_to_anchor=(0.5, 1.0), borderaxespad=0.1)
    fig.tight_layout(pad=0.4, w_pad=1.6, rect=(0, 0, 1, 0.92))
    fig.savefig(out)
    plt.close(fig)


def build() -> Path | None:
    try:
        draw(numbers(), OUT)
    except ImportError:
        print("matplotlib not installed: skipped the study's page 4 figure (pip install -r requirements.txt adds it)")
        return None
    print(f"wrote {OUT}")
    return OUT


if __name__ == "__main__":
    build()
