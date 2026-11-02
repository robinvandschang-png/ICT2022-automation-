"""Chart structure breaks and whether each one counts as displacement.

Usage:
    python -m tools.plot_structure data/nq/NQ_5min_*.csv \
        --windows "2026-03-18 08:00/2026-03-18 12:30" "2026-03-19 08:00/2026-03-19 12:30" \
        --out out/nq_displacement.png

Times in --windows are exchange time (America/New_York). Each window is one panel.
"""
from __future__ import annotations

import argparse
import glob

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ict.data import load_csv
from ict.displacement import DisplacementParams, evaluate_breaks
from ict.structure import UP, structure_breaks
from ict.swings import SwingParams, detect_swings
from ict.volatility import volatility
from tools.plot_swings import draw_candles, time_axis

TZ = "America/New_York"
PASS, FAIL = "#0F6E56", "#A32D2D"


def analyse(df: pd.DataFrame, swing_params=SwingParams(), disp_params=DisplacementParams()):
    vol = volatility(df, "tod", tz=swing_params.tz)
    swings = detect_swings(df, swing_params)
    ev = evaluate_breaks(df, structure_breaks(df, swings), vol, disp_params)
    return swings, ev


def draw_window(ax, df, swings, ev, start, end):
    local = df.index.tz_convert(TZ)
    lo = local.searchsorted(pd.Timestamp(start, tz=TZ))
    hi = local.searchsorted(pd.Timestamp(end, tz=TZ))
    draw_candles(ax, df, lo, hi)

    sw = swings[(swings["bar"] >= lo) & (swings["bar"] < hi) & swings["cancelled"].isna()]
    ax.scatter(sw["bar"], sw["price"], s=28, facecolor="none", edgecolor="#378ADD", linewidths=1.2, zorder=4)

    shown = ev[(ev["bar"] >= lo) & (ev["bar"] < hi)]
    span = df["high"].iloc[lo:hi].max() - df["low"].iloc[lo:hi].min()
    for b in shown.itertuples(index=False):
        color = PASS if b.displacement else FAIL
        x0 = max(b.swing_bar, lo)
        ax.hlines(b.swing_price, x0, b.bar, color=color, linewidth=1.3, linestyles="--", zorder=3)
        ax.plot([b.leg_start, b.bar], [b.leg_start_price, df["close"].iloc[b.bar]],
                color=color, linewidth=2.2, alpha=0.55, zorder=3)
        tag = (f"{'DISP' if b.displacement else 'weak'}\nleg {b.leg:.1f} body {b.big_body:.1f}"
               f"\neff {b.efficiency:.2f} fvg {b.fvg_count}")
        y = df["high"].iloc[b.bar] + 0.04 * span if b.direction == UP else df["low"].iloc[b.bar] - 0.04 * span
        ax.annotate(tag, (b.bar, y), fontsize=7, color=color, ha="center",
                    va="bottom" if b.direction == UP else "top")
    time_axis(ax, df, lo, hi, tz=TZ, n=9)
    ax.margins(y=0.18)
    ax.grid(alpha=0.15)
    n_pass = int(shown["displacement"].sum())
    ax.set_title(f"{pd.Timestamp(start).strftime('%a %d %b %Y')}  {pd.Timestamp(start).strftime('%H:%M')}–"
                 f"{pd.Timestamp(end).strftime('%H:%M')} ET   breaks: {len(shown)}  displacement: {n_pass}",
                 fontsize=10, loc="left")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--windows", nargs="+", required=True)
    ap.add_argument("--out", default="structure.png")
    a = ap.parse_args()
    df = load_csv(glob.glob(a.csv)[0])
    swings, ev = analyse(df)
    fig, axes = plt.subplots(len(a.windows), 1, figsize=(14, 5.2 * len(a.windows)), dpi=130, squeeze=False)
    for ax, w in zip(axes[:, 0], a.windows):
        start, end = w.split("/")
        draw_window(ax, df, swings, ev, start, end)
    fig.text(0.01, 0.005, "Dashed line = swing level broken · thick line = leg measured · "
             "green = displacement, red = weak · blue rings = tier-1 swings", fontsize=8, color="#5F5E5A")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(a.out)


if __name__ == "__main__":
    main()
