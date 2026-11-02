"""Chart raw pivots vs tiered swings so detections can be checked by eye.

Usage:
    python -m tools.plot_swings data/BTCUSDT_5m.csv --start 2026-10-28 --end 2026-10-29 \
        --k 1.0 --out out/swings.png

CSV needs a time column (first column) plus open, high, low, close.
"""
from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ict.data import load_csv
from ict.swings import SwingParams, detect_swings, raw_pivots

TIER_STYLE = {
    1: dict(s=36, facecolor="none", edgecolor="#378ADD", linewidths=1.4, label="Tier 1 short-term"),
    2: dict(s=110, facecolor="none", edgecolor="#BA7517", linewidths=1.8, label="Tier 2 intermediate"),
    3: dict(s=260, facecolor="none", edgecolor="#D85A30", linewidths=2.2, label="Tier 3 long-term"),
}


def draw_candles(ax, df: pd.DataFrame, lo: int, hi: int) -> None:
    """Candles at integer x positions lo..hi-1 (gaps such as weekends are skipped)."""
    view = df.iloc[lo:hi]
    x = range(lo, hi)
    up = view["close"] >= view["open"]
    ax.vlines(x, view["low"], view["high"], color="#888780", linewidth=0.7)
    body_lo = view[["open", "close"]].min(axis=1)
    body_h = (view["close"] - view["open"]).abs()
    ax.bar(x, body_h, bottom=body_lo, width=0.7,
           color=["#5DCAA5" if u else "#F0997B" for u in up], edgecolor="none")


def time_axis(ax, df: pd.DataFrame, lo: int, hi: int, tz: str | None = None, n: int = 10) -> None:
    idx = df.index if tz is None else df.index.tz_convert(tz)
    ticks = list(range(lo, hi, max(1, (hi - lo) // n)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([idx[i].strftime("%m-%d %H:%M") for i in ticks], fontsize=8)
    ax.set_xlim(lo - 1, hi)


def plot_swings(df: pd.DataFrame, params: SwingParams, start=None, end=None,
                out: str = "swings.png", title: str = "") -> dict:
    """Detect on the full history (for warm-up), draw only [start, end]."""
    swings = detect_swings(df, params)
    pivots = raw_pivots(df, params.pivot_bars)

    tz = params.tz if df.index.tz is not None else None  # window times are exchange time
    local = df.index if tz is None else df.index.tz_convert(tz)
    lo = 0 if start is None else local.searchsorted(pd.Timestamp(start, tz=tz))
    hi = len(df) if end is None else local.searchsorted(pd.Timestamp(end, tz=tz))

    fig, ax = plt.subplots(figsize=(14, 6.5), dpi=130)
    draw_candles(ax, df, lo, hi)

    pv = pivots[(pivots["bar"] >= lo) & (pivots["bar"] < hi)]
    ax.scatter(pv["bar"], pv["price"], s=10, color="#5F5E5A", zorder=3,
               label=f"Raw pivots ({len(pv)})")

    sw = swings[(swings["bar"] >= lo) & (swings["bar"] < hi) & swings["cancelled"].isna()]
    counts = {}
    for tier in (1, 2, 3):
        t = sw[sw["tier"] >= tier]
        counts[tier] = len(t)
        style = dict(TIER_STYLE[tier])
        style["label"] = f"{style['label']} ({len(t)})"
        ax.scatter(t["bar"], t["price"], zorder=4 + tier, **style)

    time_axis(ax, df, lo, hi, tz=tz)
    ax.grid(alpha=0.15)
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    ax.set_title(title or f"Swings  (pivot_bars={params.pivot_bars}, min_move_atr={params.min_move_atr})",
                 fontsize=11, loc="left")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return {"raw": len(pv), **{f"tier{k}": v for k, v in counts.items()}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--k", type=float, default=1.0)
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--out", default="swings.png")
    a = ap.parse_args()
    df = load_csv(a.csv)  # tz-aware, so the time-of-day yardstick uses exchange time
    print(plot_swings(df, SwingParams(pivot_bars=a.n, min_move_atr=a.k), a.start, a.end, a.out))


if __name__ == "__main__":
    main()
